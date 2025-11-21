# backend/api/main.py

from typing import List, Optional

from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel

from opensearchpy import OpenSearch

from backend.config import OPENSEARCH_HOST, TRIALS_INDEX_NAME
from backend.db.scrape_clinical_trials import fetch_and_store
from backend.search.reindex_from_postgres import reindex as run_reindex
from backend.db.init_db import run_schema
from backend.search.init_index import create_index


# -----------------------------
# OpenSearch client
# -----------------------------
def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[OPENSEARCH_HOST],
        http_compress=True,
    )


client = get_opensearch_client()

app = FastAPI(
    title="Clinical Trial Search API",
    version="1.0.0",
)


# -----------------------------
# Response models
# -----------------------------
class TrialHit(BaseModel):
    nct_id: str
    title: Optional[str] = None
    brief_summary: Optional[str] = None
    phase: Optional[str] = None
    overall_status: Optional[str] = None
    conditions: List[str] = []
    study_type: Optional[str] = None
    locations: List[str] = []
    score: float


class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    hits: List[TrialHit]

class ScrapeRequest(BaseModel):
    max_studies: int = 1000          # how many to try to ingest in this run
    page_size: int = 100             # API page size (<= 100)
    condition: Optional[str] = None  # optional filter, e.g. "lung cancer"

class IndexRequest(BaseModel):
    chunk_size: int = 1000
    refresh: bool = True

# -----------------------------
# Helper: build OpenSearch query
# -----------------------------
def build_query(
    q: Optional[str],
    phase: Optional[str],
    status: Optional[str],
    condition: Optional[str],
    country: Optional[str],
):
    must_clauses = []
    filter_clauses = []

    if q:
        must_clauses.append(
            {
                "multi_match": {
                    "query": q,
                    "fields": [
                        "title^3",
                        "brief_summary^2",
                        "detailed_description",
                        "conditions^2",
                        "interventions",
                        "criteria_inclusion",
                        "criteria_exclusion",
                    ],
                    "type": "best_fields",
                    "operator": "and",
                }
            }
        )
    else:
        must_clauses.append({"match_all": {}})

    if phase:
        filter_clauses.append({"term": {"phase": phase}})

    if status:
        filter_clauses.append({"term": {"overall_status": status}})

    if condition:
        # use match here so partial condition names work ('lung cancer', 'diabetes')
        filter_clauses.append(
            {"match": {"conditions": {"query": condition, "operator": "and"}}}
        )

    if country:
        # locations is nested, so use nested filter
        filter_clauses.append(
            {
                "nested": {
                    "path": "locations",
                    "query": {
                        "term": {
                            "locations.country": country
                        }
                    },
                }
            }
        )

    query = {
        "bool": {
            "must": must_clauses,
            "filter": filter_clauses,
        }
    }
    return query


# -----------------------------
# Routes
# -----------------------------
@app.get("/health", tags=["health"])
def health():
    try:
        if not client.ping():
            raise HTTPException(status_code=503, detail="OpenSearch not responding")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/search", response_model=SearchResponse, tags=["search"])
def search_trials(
    q: Optional[str] = Query(
        None,
        description="Free-text query over title, summary, description, conditions, criteria",
    ),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    phase: Optional[str] = Query(
        None,
        description="Filter by phase (e.g. 'Phase 1', 'Phase 2', 'Phase 3')",
    ),
    overall_status: Optional[str] = Query(
        None,
        description="Filter by overall_status (e.g. 'Recruiting', 'Completed')",
    ),
    condition: Optional[str] = Query(
        None,
        description="Filter by condition text (e.g. 'lung cancer')",
    ),
    country: Optional[str] = Query(
        None,
        description="Filter by country code/name in locations (exact term)",
    ),
):
    """
    Search clinical trials using BM25 (OpenSearch).

    - q: full-text search query
    - phase: exact phase filter (keyword)
    - overall_status: exact status filter (keyword)
    - condition: extra match filter over 'conditions'
    - country: filter by site country (nested locations)
    """
    from_ = (page - 1) * size

    query = build_query(q, phase, overall_status, condition, country)

    body = {
        "from": from_,
        "size": size,
        "query": query,
        "_source": [
            "nct_id",
            "title",
            "brief_summary",
            "detailed_description",
            "phase",
            "overall_status",
            "conditions",
            "study_type",
            "locations",
        ],
    }

    try:
        res = client.search(index=TRIALS_INDEX_NAME, body=body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    total = res.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        total_value = total.get("value", 0)
    else:
        total_value = total or 0

    hits: List[TrialHit] = []

    for h in res.get("hits", {}).get("hits", []):
        src = h.get("_source", {})
        score = h.get("_score", 0.0)

        locs = src.get("locations") or []
        loc_strings = []
        for loc in locs:
            parts = [
                loc.get("city"),
                loc.get("state"),
                loc.get("country"),
            ]
            loc_strings.append(", ".join([p for p in parts if p]))

        hit = TrialHit(
            nct_id=src.get("nct_id"),
            title=src.get("title"),
            brief_summary=src.get("brief_summary"),
            phase=src.get("phase"),
            overall_status=src.get("overall_status"),
            conditions=src.get("conditions") or [],
            study_type=src.get("study_type"),
            locations=loc_strings,
            score=score,
        )
        hits.append(hit)

    return SearchResponse(
        total=total_value,
        page=page,
        size=size,
        hits=hits,
    )

@app.post("/admin/scrape", tags=["admin"])
def trigger_scrape(
    body: ScrapeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a background scrape from the ClinicalTrials.gov v2 API into Postgres.

    This just kicks off the job and returns immediately.
    Check logs / DB to see progress.
    """
    # schedule the scraping as a background task so the HTTP call returns quickly
    background_tasks.add_task(
        fetch_and_store,
        max_studies=body.max_studies,
        condition=body.condition,
        page_size=body.page_size,
    )

    return {
        "status": "started",
        "max_studies": body.max_studies,
        "page_size": body.page_size,
        "condition": body.condition,
    }

@app.post("/admin/index", tags=["admin"])
def index_data(
    body: IndexRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger reindexing of all trials from Postgres into OpenSearch.

    - Runs in the background
    - Returns immediately
    """
    background_tasks.add_task(
        run_reindex,
        chunk_size=body.chunk_size,
        refresh=body.refresh
    )

    return {
        "status": "started",
        "chunk_size": body.chunk_size,
        "refresh": body.refresh
    }

@app.post("/admin/init-index", tags=["admin"])
def init_index_endpoint():
    try:
        create_index()
        return {"status": "index created"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/admin/init-db", tags=["admin"])
def init_db_endpoint():
    """
    Initialize database schema (creates trials, sites, criteria tables).
    Safe to run multiple times.
    """
    try:
        run_schema()
        return {"status": "db initialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
