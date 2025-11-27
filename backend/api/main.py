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
from backend.search.vector_search import get_vector_search
from backend.search.build_faiss_index import build_faiss_index

# -----------------------------
# OpenSearch client
# -----------------------------
def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[OPENSEARCH_HOST],
        http_compress=True,
    )


client = get_opensearch_client()
vector_search = get_vector_search()

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

class RankRequest(BaseModel):
    """
    Request body for /rank: uses a free-text patient profile as the query.
    You can extend this later with structured fields (age, sex, etc.).
    """
    patient_profile: str
    page: int = 1
    size: int = 10
    phase: Optional[str] = None
    overall_status: Optional[str] = None
    condition: Optional[str] = None
    country: Optional[str] = None
    bm25_weight: float = 0.5


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
                    # Looser, works for both short + long queries
                    "operator": "or",
                    "minimum_should_match": "60%",
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
        filter_clauses.append(
            {
                "match": {
                    "conditions": {
                        "query": condition,
                        "operator": "and",
                    }
                }
            }
        )

    if country:
        filter_clauses.append(
            {
                "nested": {
                    "path": "locations",
                    "query": {"term": {"locations.country": country}},
                }
            }
        )

    return {
        "bool": {
            "must": must_clauses,
            "filter": filter_clauses,
        }
    }


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

def _normalize_scores(values: List[float]) -> dict[str, float]:
    if not values:
        return {}
    v_min = min(values)
    v_max = max(values)
    if v_max <= v_min:
        # all equal → everything becomes 1.0
        return {str(i): 1.0 for i in range(len(values))}
    norm = {}
    for i, v in enumerate(values):
        norm[str(i)] = (v - v_min) / (v_max - v_min)
    return norm


def _search_trials_internal(
    q: Optional[str],
    page: int,
    size: int,
    phase: Optional[str],
    overall_status: Optional[str],
    condition: Optional[str],
    country: Optional[str],
    bm25_weight: float = 0.5,
) -> SearchResponse:
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if size < 1 or size > 100:
        raise HTTPException(status_code=400, detail="size must be between 1 and 100")
    if not (0.0 <= bm25_weight <= 1.0):
        raise HTTPException(status_code=400, detail="bm25_weight must be in [0, 1]")

    query = build_query(
        q=q,
        phase=phase,
        status=overall_status,
        condition=condition,
        country=country,
    )

    from_ = (page - 1) * size

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

    # --- BM25 search (OpenSearch) ---
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
    bm25_scores: List[float] = []

    for h in res.get("hits", {}).get("hits", []):
        src = h.get("_source", {})
        score = float(h.get("_score", 0.0))

        locs = src.get("locations") or []
        loc_strings: List[str] = []
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
            score=score,  # temporarily BM25 score
        )
        hits.append(hit)
        bm25_scores.append(score)

    # --- Dense retrieval (FAISS) + hybrid fusion ---
    if q and vector_search.ready and hits:
        # more candidates than just "size" can help, but we keep it simple
        dense_results = vector_search.search(q, k=max(size * 3, size))

        dense_by_id = {nct_id: s for (nct_id, s) in dense_results}

        # normalize BM25 & dense scores to [0, 1]
        bm25_norm_map = _normalize_scores(bm25_scores)
        dense_norm_values = list(dense_by_id.values())
        dense_norm_map_raw = _normalize_scores(dense_norm_values)
        # map back to nct_id → norm_dense
        dense_norm_by_id: dict[str, float] = {}
        for idx, (nct_id, s) in enumerate(dense_results):
            key = str(idx)
            if key in dense_norm_map_raw:
                dense_norm_by_id[nct_id] = dense_norm_map_raw[key]

        # hybrid = w * bm25_norm + (1 - w) * dense_norm
        for i, hit in enumerate(hits):
            bm25_norm = float(bm25_norm_map.get(str(i), 0.0))
            dense_norm = float(dense_norm_by_id.get(hit.nct_id, 0.0))
            hybrid = bm25_weight * bm25_norm + (1.0 - bm25_weight) * dense_norm
            hit.score = hybrid

        # sort by hybrid score desc
        hits.sort(key=lambda h: h.score, reverse=True)

    # if FAISS not ready or no q, we just return BM25 scores as-is
    return SearchResponse(
        total=total_value,
        page=page,
        size=size,
        hits=hits,
    )

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
    bm25_weight: float = Query(
        0.5,
        ge=0.0,
        le=1.0,
        description="Weight for BM25 in hybrid fusion (dense weight = 1 - bm25_weight)",
    ),
):
    """
    Hybrid search over clinical trials.

    - BM25 via OpenSearch
    - Dense retrieval via MiniLM + FAISS (if index is built)
    - Scores combined via weighted sum (bm25_weight vs. dense weight)
    """
    return _search_trials_internal(
        q=q,
        page=page,
        size=size,
        phase=phase,
        overall_status=overall_status,
        condition=condition,
        country=country,
        bm25_weight=bm25_weight,
    )

@app.post("/rank", response_model=SearchResponse, tags=["ranking"])
def rank_trials(body: RankRequest):
    """
    Rank trials for a given patient profile.

    The `patient_profile` is treated as a free-text query that feeds both:
    - BM25 (OpenSearch) over trial documents
    - Dense retrieval (MiniLM + FAISS) when available

    The result is a ranked list of trials with hybrid scores.
    """
    return _search_trials_internal(
        q=body.patient_profile,
        page=body.page,
        size=body.size,
        phase=body.phase,
        overall_status=body.overall_status,
        condition=body.condition,
        country=body.country,
        bm25_weight=body.bm25_weight,
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

@app.post("/admin/build-faiss", tags=["admin"])
def admin_build_faiss(background_tasks: BackgroundTasks):
    """
    Trigger async FAISS index building without blocking the API request.
    Returns 200 immediately.
    """
    background_tasks.add_task(build_faiss_index)
    return {"status": "started"}