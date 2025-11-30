# backend/api/main.py

from typing import List, Optional, Dict
import logging

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
from backend.nlp import FeasibilityScorer

# -----------------------------
# OpenSearch client
# -----------------------------
logger = logging.getLogger(__name__)


def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[OPENSEARCH_HOST],
        http_compress=True,
    )


client = get_opensearch_client()
vector_search = get_vector_search()
feasibility_scorer = FeasibilityScorer()

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
    retrieval_score: Optional[float] = None
    retrieval_score_raw: Optional[float] = None
    feasibility_score: Optional[float] = None
    feasibility_reasons: Optional[List[str]] = None
    is_feasible: Optional[bool] = None


class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    hits: List[TrialHit]
    candidate_total: Optional[int] = None
    truncated: bool = False


class ScrapeRequest(BaseModel):
    max_studies: int = 1000          # how many to try to ingest in this run
    page_size: int = 100             # API page size (<= 100)
    condition: Optional[str] = None  # optional filter, e.g. "lung cancer"


class IndexRequest(BaseModel):
    chunk_size: int = 1000
    refresh: bool = True


# -----------------------------
# Patient profile models (JSON input for /rank)
# -----------------------------
class PatientProfile(BaseModel):
    age: int
    gender: str

    conditions: List[str] = []
    ecog: Optional[int] = None

    biomarkers: List[str] = []
    history: List[str] = []

    labs: Dict[str, Optional[float]] = {} 

    prior_lines: Optional[int] = None
    days_since_last_treatment: Optional[int] = None


class RankRequest(BaseModel):
    """
    Structured patient profile for /rank, plus optional filters and weights.
    """
    profile: PatientProfile
    phase: Optional[str] = None
    overall_status: Optional[str] = None
    condition: Optional[str] = None
    country: Optional[str] = None
    bm25_weight: float = 0.5
    feasibility_weight: float = 0.6


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
# Helper: build text query from PatientProfile
# -----------------------------
def build_profile_query_text(profile: PatientProfile) -> str:
    """
    Turn structured JSON profile into a compact natural-language query
    that can be used by both BM25 (OpenSearch) and FAISS (MiniLM).
    """
    parts: List[str] = []

    # Age + gender
    gender_word = profile.gender.lower()
    if gender_word in ("m", "male"):
        gender_str = "male"
    elif gender_word in ("f", "female"):
        gender_str = "female"
    else:
        gender_str = profile.gender

    parts.append(f"{profile.age}-year-old {gender_str}")

    # Conditions
    if profile.conditions:
        parts.append("with " + ", ".join(profile.conditions))

    # ECOG
    if profile.ecog is not None:
        parts.append(f"ECOG performance status {profile.ecog}")

    # Biomarkers
    if profile.biomarkers:
        parts.append("Biomarkers: " + ", ".join(profile.biomarkers))

    # History / comorbidities
    if profile.history:
        parts.append("History of " + ", ".join(profile.history))

    # Prior lines and recent treatment
    if profile.prior_lines is not None:
        parts.append(f"{profile.prior_lines} prior lines of systemic therapy")
    if profile.days_since_last_treatment is not None:
        parts.append(f"{profile.days_since_last_treatment} days since last treatment")

    # We could also add selective labs if desired, but this is already rich
    return ". ".join(parts)


# -----------------------------
# Health route
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


def _build_criteria_text(src: dict) -> str:
    """
    Combine inclusion/exclusion strings into one block for feasibility scoring.
    """
    parts: List[str] = []
    raw_block = src.get("eligibility_criteria_raw")
    if raw_block:
        parts.append(raw_block)
    incl = src.get("criteria_inclusion")
    if incl:
        parts.append(f"Inclusion: {incl}")
    excl = src.get("criteria_exclusion")
    if excl:
        parts.append(f"Exclusion: {excl}")
    return "\n".join(parts).strip()


def _apply_feasibility_rerank(
    hits: List[TrialHit],
    criteria_by_id: dict[str, str],
    patient_profile: PatientProfile,
    feasibility_weight: float,
) -> None:
    """
    Run the NLP feasibility scorer for each hit and blend with retrieval scores.

    - Retrieval scores are normalized to [0,1] before blending.
    - Feasibility scores are 0-100; normalized to [0,1].
    - Final score = (1 - feasibility_weight) * retrieval_norm + feasibility_weight * feasibility_norm
    """
    if not hits:
        return
    if not (0.0 <= feasibility_weight <= 1.0):
        raise HTTPException(
            status_code=400,
            detail="feasibility_weight must be between 0 and 1",
        )

    profile_dict = patient_profile.dict()

    retrieval_raw_values: List[float] = []
    for hit in hits:
        base = hit.retrieval_score_raw
        if base is None:
            base = hit.score
        retrieval_raw_values.append(float(base))

    if retrieval_raw_values:
        v_min = min(retrieval_raw_values)
        v_max = max(retrieval_raw_values)
    else:
        v_min = v_max = 0.0

    def _norm(val: float) -> float:
        if v_max <= v_min:
            return 1.0
        return (val - v_min) / (v_max - v_min)

    for idx, hit in enumerate(hits):
        retrieval_norm = _norm(retrieval_raw_values[idx])
        hit.retrieval_score = retrieval_norm

        criteria_text = criteria_by_id.get(hit.nct_id, "")
        if not criteria_text:
            hit.feasibility_score = None
            hit.feasibility_reasons = ["No eligibility criteria available"]
            hit.is_feasible = None
            feasibility_norm = 0.0
        else:
            try:
                result = feasibility_scorer.score_patient(profile_dict, criteria_text)
                feas_score = float(result.get("score") or 0.0)
                hit.feasibility_score = feas_score
                hit.feasibility_reasons = result.get("reasons") or []
                hit.is_feasible = bool(result.get("is_feasible"))
                feasibility_norm = feas_score / 100.0
            except Exception as exc:  # pragma: no cover - safety net
                hit.feasibility_score = None
                hit.feasibility_reasons = [f"Feasibility scoring error: {exc}"]
                hit.is_feasible = None
                feasibility_norm = 0.0
                logger.exception("Feasibility scoring failed for nct_id=%s", hit.nct_id)

        hit.score = (1.0 - feasibility_weight) * retrieval_norm + feasibility_weight * feasibility_norm

    hits.sort(key=lambda h: h.score, reverse=True)


def _search_trials_internal(
    q: Optional[str],
    page: int,
    size: int,
    phase: Optional[str],
    overall_status: Optional[str],
    condition: Optional[str],
    country: Optional[str],
    bm25_weight: float = 0.5,
    candidate_size: Optional[int] = None,
    patient_profile: Optional[PatientProfile] = None,
    feasibility_weight: float = 0.6,
    use_candidate_total: bool = False,
) -> SearchResponse:
    """
    Internal search helper.

    - BM25 via OpenSearch over 'candidate_size' docs (defaults to 'size')
    - Dense retrieval via FAISS (MiniLM) using 'q'
    - Hybrid fusion of scores
    - Optional feasibility scoring and re-ranking using NLP eligibility parser
    - Returns a page of results (page, size) out of the BM25 candidate set.
    """
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if size < 1 or size > 100:
        raise HTTPException(status_code=400, detail="size must be between 1 and 100")
    if not (0.0 <= bm25_weight <= 1.0):
        raise HTTPException(status_code=400, detail="bm25_weight must be in [0, 1]")
    if patient_profile and not (0.0 <= feasibility_weight <= 1.0):
        raise HTTPException(status_code=400, detail="feasibility_weight must be in [0, 1]")

    # How many docs to ask BM25 for in total (candidate pool)
    total_candidates = candidate_size or size

    query = build_query(
        q=q,
        phase=phase,
        status=overall_status,
        condition=condition,
        country=country,
    )

    # We always fetch from offset 0 for the candidate pool;
    # pagination is done after hybrid scoring.
    body = {
        "from": 0,
        "size": total_candidates,
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
            "criteria_inclusion",
            "criteria_exclusion",
            "eligibility_criteria_raw",
        ],
    }

    # --- BM25 search (OpenSearch) ---
    try:
        res = client.search(index=TRIALS_INDEX_NAME, body=body)
    except Exception as e:
        logger.exception("OpenSearch query failed")
        raise HTTPException(status_code=500, detail=str(e))

    total = res.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        total_value = total.get("value", 0)
    else:
        total_value = total or 0

    hits: List[TrialHit] = []
    bm25_scores: List[float] = []
    criteria_by_id: dict[str, str] = {}

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
            retrieval_score_raw=score,
        )
        hits.append(hit)
        bm25_scores.append(score)
        if patient_profile:
            criteria_by_id[hit.nct_id] = _build_criteria_text(src)
    # If BM25 yields no results → fallback to dense-only
    if not hits and q and vector_search.ready:
        logger.info("BM25 returned no hits; falling back to dense-only search")
        return dense_only_fallback(
            q,
            page,
            size,
            patient_profile=patient_profile,
            feasibility_weight=feasibility_weight,
            use_candidate_total=use_candidate_total,
        )

    # --- Dense retrieval (FAISS) + hybrid fusion ---
    if q and vector_search.ready and hits:
        # Use a reasonably large k for dense candidates; keep it tied to total_candidates
        dense_results = vector_search.search(q, k=max(total_candidates * 3, total_candidates))

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
            hit.retrieval_score_raw = hybrid

        # sort by hybrid score desc
        hits.sort(key=lambda h: h.score, reverse=True)

    # Optional feasibility scoring + blending
    if patient_profile:
        _apply_feasibility_rerank(
            hits=hits,
            criteria_by_id=criteria_by_id,
            patient_profile=patient_profile,
            feasibility_weight=feasibility_weight,
        )

    # Pagination over the candidate set after hybrid scoring
    start = (page - 1) * size
    end = start + size
    page_hits = hits[start:end]

    candidate_total = len(hits)
    response_total = candidate_total if use_candidate_total else total_value
    truncated = use_candidate_total and total_value > candidate_total

    return SearchResponse(
        total=response_total,
        page=page,
        size=size,
        hits=page_hits,
        candidate_total=candidate_total if use_candidate_total else None,
        truncated=truncated,
    )


def dense_only_fallback(
    q: str,
    page: int,
    size: int,
    patient_profile: Optional[PatientProfile] = None,
    feasibility_weight: float = 0.6,
    use_candidate_total: bool = False,
) -> SearchResponse:
    # Step 1: FAISS dense retrieval
    logger.info("Entering dense-only fallback (FAISS) for query")
    dense_results = vector_search.search(q, k=max(size * 5, 100))

    if not dense_results:
        logger.warning("Dense-only fallback returned no results")
        return SearchResponse(total=0, page=page, size=size, hits=[])

    nct_ids = [n for (n, _) in dense_results]

    # Step 2: Fetch docs by NCT ID using OpenSearch terms query
    body = {
        "query": {"terms": {"nct_id": nct_ids}},
        "size": len(nct_ids),
        "_source": [
            "nct_id", "title", "brief_summary", "phase",
            "overall_status", "conditions", "study_type", "locations",
            "criteria_inclusion", "criteria_exclusion", "eligibility_criteria_raw"
        ]
    }

    res = client.search(index=TRIALS_INDEX_NAME, body=body)

    # Step 3: Normalize dense scores
    dense_by_id = {n: float(s) for (n, s) in dense_results}
    scores = list(dense_by_id.values())
    norm_map = _normalize_scores(scores)

    # Step 4: Build hits
    hits: List[TrialHit] = []
    criteria_by_id: dict[str, str] = {}
    for i, h in enumerate(res["hits"]["hits"]):
        src = h["_source"]
        nct = src["nct_id"]
        score = norm_map.get(str(i), 0.0)
        raw_dense = dense_by_id.get(nct, 0.0)

        locations = []
        for loc in src.get("locations", []):
            parts = [loc.get("city"), loc.get("state"), loc.get("country")]
            locations.append(", ".join([p for p in parts if p]))

        hits.append(
            TrialHit(
                nct_id=nct,
                title=src.get("title"),
                brief_summary=src.get("brief_summary"),
                phase=src.get("phase"),
                overall_status=src.get("overall_status"),
                conditions=src.get("conditions") or [],
                study_type=src.get("study_type"),
                locations=locations,
                score=score,
                retrieval_score_raw=raw_dense,
            )
        )
        criteria_by_id[nct] = _build_criteria_text(src)

    # Step 5: Optional feasibility blending, then sort and paginate
    if patient_profile:
        _apply_feasibility_rerank(
            hits=hits,
            criteria_by_id=criteria_by_id,
            patient_profile=patient_profile,
            feasibility_weight=feasibility_weight,
        )
    else:
        hits.sort(key=lambda h: h.score, reverse=True)
    start = (page - 1) * size
    end = start + size

    candidate_total = len(hits)
    response_total = candidate_total if use_candidate_total else candidate_total

    return SearchResponse(
        total=response_total,
        page=page,
        size=size,
        hits=hits[start:end],
        candidate_total=candidate_total if use_candidate_total else None,
        truncated=False,
    )


# -----------------------------
# Routes
# -----------------------------
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
    Hybrid search over clinical trials (free-text query).

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
        candidate_size=size,  # for /search, candidate pool = requested page size
    )


@app.post("/rank", response_model=SearchResponse, tags=["ranking"])
def rank_trials(body: RankRequest):
    """
    Rank trials for a given structured patient profile (JSON).

    - The profile JSON is converted into a compact text query.
    - That query is fed to:
        - BM25 (OpenSearch) over trial documents
        - Dense retrieval (MiniLM + FAISS) when available
    - We always fetch up to 100 BM25 candidates, apply hybrid scoring,
      optionally blend with the NLP feasibility score, and then return the
      requested page/size from that candidate set.
    """
    q_text = build_profile_query_text(body.profile)

    # Always search over a candidate pool of 100 docs for /rank,
    # but only return the top 20 to clients.
    candidate_size = 100
    page = 1
    size = 20

    return _search_trials_internal(
        q=q_text,
        page=page,
        size=size,
        phase=body.phase,
        overall_status=body.overall_status,
        condition=body.condition,
        country=body.country,
        bm25_weight=body.bm25_weight,
        candidate_size=candidate_size,
        patient_profile=body.profile,
        feasibility_weight=body.feasibility_weight,
        use_candidate_total=True,
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
