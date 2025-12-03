# backend/api/main.py

from typing import Any, List, Optional, Dict
import logging
import time

import psycopg2
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, validator
from psycopg2.extras import RealDictCursor

from opensearchpy import OpenSearch
from fastapi.middleware.cors import CORSMiddleware

from backend.config import OPENSEARCH_HOST, TRIALS_INDEX_NAME
from backend.config import POSTGRES_DSN
from backend.db.scrape_clinical_trials import fetch_and_store
from backend.search.reindex_from_postgres import reindex as run_reindex
from backend.db.init_db import run_schema
from backend.search.init_index import create_index
from backend.search.vector_search import get_vector_search
from backend.search.build_faiss_index import build_faiss_index
from backend.nlp import FeasibilityScorer
from backend.nlp.condition_normalizer import get_condition_normalizer
from backend.nlp.biomarker_normalizer import get_biomarker_normalizer

# -----------------------------
# OpenSearch client
# -----------------------------
logging.basicConfig(level=logging.INFO)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("Pre-loading UMLS Linker...")
    # Trigger lazy load
    feasibility_scorer._get_umls()
    logger.info("UMLS Linker pre-loaded.")
    
    # Pre-load vector search model
    if vector_search.ready:
        logger.info("Pre-loading Vector Search model...")
        # Trigger model loading with a dummy query
        vector_search.search("test", k=1)
        logger.info("Vector Search model pre-loaded.")

# -----------------------------
# Response models
# -----------------------------
class TrialHit(BaseModel):
    nct_id: str
    title: Optional[str] = None
    brief_summary: Optional[str] = None
    phase: Optional[str] = None
    overall_status: Optional[str] = None
    conditions: Optional[List[str]] = None
    conditions_cuis: Optional[List[str]] = None
    study_type: Optional[str] = None
    locations: Optional[List[str]] = None
    score: float = 0.0
    retrieval_score: Optional[float] = None
    retrieval_score_raw: Optional[float] = None
    feasibility_score: Optional[float] = None
    feasibility_reasons: Optional[List[str]] = None
    is_feasible: Optional[bool] = None
    eligibility_criteria_raw: Optional[str] = None
    parsed_criteria: Optional[Dict[str, Any]] = None
    min_age_years: Optional[float] = None 
    max_age_years: Optional[float] = None  
    sex: Optional[str] = None

    @validator("conditions", "conditions_cuis", "locations", "feasibility_reasons", pre=True)
    def _default_empty_list(cls, v):
        return v or []

    class Config:
        extra = "forbid"


class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    hits: List[TrialHit]
    candidate_total: Optional[int] = None
    truncated: bool = False


class TrialLocation(BaseModel):
    facility_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


class TrialDetail(BaseModel):
    nct_id: str
    title: Optional[str] = None
    official_title: Optional[str] = None
    brief_summary: Optional[str] = None
    detailed_description: Optional[str] = None
    conditions: List[str] = Field(default_factory=list)
    interventions: List[str] = Field(default_factory=list)
    study_type: Optional[str] = None
    phase: Optional[str] = None
    overall_status: Optional[str] = None
    min_age_years: Optional[int] = None
    max_age_years: Optional[int] = None
    sex: Optional[str] = None
    healthy_volunteers: Optional[bool] = None
    enrollment_actual: Optional[int] = None
    enrollment_target: Optional[int] = None
    start_date: Optional[str] = None
    primary_completion_date: Optional[str] = None
    completion_date: Optional[str] = None
    last_updated: Optional[str] = None
    locations: List[TrialLocation] = Field(default_factory=list)
    criteria_inclusion: Optional[str] = None
    criteria_exclusion: Optional[str] = None
    eligibility_criteria_raw: Optional[str] = None


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

    # Allow these list fields to be nullable in incoming JSON; coerce None -> []
    conditions: Optional[List[str]] = None
    ecog: Optional[int] = None

    biomarkers: Optional[List[str]] = None
    history: Optional[List[str]] = None

    labs: Dict[str, Optional[float]] = {}

    prior_lines: Optional[int] = None
    days_since_last_treatment: Optional[int] = None

    @validator("conditions", "biomarkers", "history", pre=True, always=True)
    def _default_empty_list(cls, v):  # type: ignore
        return v or []


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
    age: Optional[int] = None,
    gender: Optional[str] = None,
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
                        "conditions^4",
                        "conditions_all^5",
                        "interventions",
                        "criteria_inclusion_clean^2"
                    ],
                    "type": "best_fields",
                    # Looser, works for both short + long queries
                    "operator": "or",
                    # "minimum_should_match": "60%",
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
    # Age Logic: Trial Min <= Patient Age <= Trial Max
    if age is not None:
        filter_clauses.append({
            "range": {
                "min_age_years": {"lte": age} # Trial min must be <= Patient age
            }
        })
        filter_clauses.append({
            "range": {
                "max_age_years": {"gte": age} # Trial max must be >= Patient age
            }
        })

    # Gender Logic: Trial Sex must match Patient OR be "ALL"
    if gender and gender.lower() != "all":
        # We allow trials that are specifically for this gender OR for "ALL"
        target_gender = gender.upper() # "MALE" or "FEMALE"
        filter_clauses.append({
            "terms": {
                "sex": [target_gender, "ALL"]
            }
        })

    bool_query = {
        "bool": {
            "must": must_clauses,
            "filter": filter_clauses,
        }
    }

    # Wrap in function_score to boost Recruiting and Late Phase trials
    query_body = {
        "function_score": {
            "query": bool_query,
            "functions": [
                {
                    "filter": {"term": {"overall_status.keyword": "Recruiting"}},
                    "weight": 1.05
                },
                {
                    "filter": {"terms": {"phase.keyword": ["Phase 3", "Phase 4"]}},
                    "weight": 1.1
                },
                {
                    "filter": {"terms": {"phase.keyword": ["Phase 2"]}},
                    "weight": 1.05
                }
            ],
            "score_mode": "multiply",
            "boost_mode": "multiply"
        }
    }

    return query_body


# -----------------------------
# Helper: build text query from PatientProfile
# -----------------------------
def build_profile_query_text(profile: PatientProfile) -> str:
    """
    Turn structured JSON profile into a compact natural-language query
    that can be used by both BM25 (OpenSearch) and FAISS (MiniLM).
    """
    parts: List[str] = []

    # Age + gender - REMOVED to prevent recall drop (we filter by age/gender anyway)
    # gender_word = profile.gender.lower()
    # if gender_word in ("m", "male"):
    #     gender_str = "male"
    # elif gender_word in ("f", "female"):
    #     gender_str = "female"
    # else:
    #     gender_str = profile.gender

    # parts.append(f"{profile.age}-year-old {gender_str}")

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


def _expand_condition_synonyms_for_query(normalized_conditions: List[str], max_terms: int = 8, max_per_condition: int = 3) -> List[str]:
    try:
        normalizer = get_condition_normalizer()
    except Exception:
        return []

    expanded: List[str] = []
    seen = set()
    for key in normalized_conditions:
        terms = normalizer.get_all_synonyms(key)[: max_per_condition]
        for t in terms:
            tl = t.lower().strip()
            if tl and tl not in seen and len(expanded) < max_terms:
                expanded.append(t)
                seen.add(tl)
        if len(expanded) >= max_terms:
            break
    return expanded


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
    
#normalise condition input
def normalize_condition_input(user_text: str) -> str:
    """
    Maps user text to internal canonical keys 
    """
    normalizer = get_condition_normalizer()
    normalized = normalizer.normalize(user_text)
    # If no match found, return original text in Title Case
    return normalized if normalized else user_text.title()


def compute_rrf(rank_lists: List[List[str]], k: int = 20) -> Dict[str, float]:
    """
    Compute Reciprocal Rank Fusion scores.
    rank_lists: List of lists, where each inner list contains nct_ids in ranked order.
    Returns: Dict mapping nct_id -> rrf_score
    """
    rrf_map = {}
    for rank_list in rank_lists:
        for rank, nct_id in enumerate(rank_list):
            if nct_id not in rrf_map:
                rrf_map[nct_id] = 0.0
            rrf_map[nct_id] += 1.0 / (k + rank + 1)
    return rrf_map


def _normalize_scores(scores: List[float]) -> Dict[str, float]:
    """
    Min-Max normalization of scores.
    Returns a dict mapping index -> normalized score.
    """
    if not scores:
        return {}
    min_s = min(scores)
    max_s = max(scores)
    if max_s == min_s:
        return {str(i): 1.0 for i in range(len(scores))}
    return {str(i): (s - min_s) / (max_s - min_s) for i, s in enumerate(scores)}


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
        base = hit.score
        if base is None:
            base = 0.0
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

    # Pre-compute patient CUIs to avoid re-running NLP for every trial
    patient_cuis = None
    if patient_profile.conditions:
        # We need to access the scorer instance. It's global 'feasibility_scorer'.
        patient_cuis = feasibility_scorer.extract_cuis(patient_profile.conditions)

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
                metadata = {
                    "min_age_years": hit.min_age_years,
                    "max_age_years": hit.max_age_years,
                    "sex": hit.sex,
                    "conditions": hit.conditions or [],
                    "conditions_cuis": hit.conditions_cuis or [],
                    "parsed_criteria": hit.parsed_criteria
                }
                result = feasibility_scorer.score_patient(
                    profile_dict, 
                    criteria_text, 
                    trial_metadata=metadata,
                    patient_cuis=patient_cuis
                )
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
    # Remove trials explicitly marked as infeasible (is_feasible == False)
    # Keep those where feasibility wasn't assessed (None) or passed (True)
    hits[:] = [h for h in hits if getattr(h, 'is_feasible', None) is not False]


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

    filter_age = None
    filter_gender = None
    if patient_profile:
        filter_age = patient_profile.age
        filter_gender = patient_profile.gender

    query = build_query(
        q=q,
        phase=phase,
        status=overall_status,
        condition=condition,
        country=country,
        age=filter_age,
        gender=filter_gender
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
            "conditions_cuis",
            "study_type",
            "locations",
            "criteria_inclusion",
            "criteria_exclusion",
            "eligibility_criteria_raw",
            "parsed_criteria",
            "min_age_years",
            "max_age_years",
            "sex",
            "healthy_volunteers",
            "enrollment"
        ],
    }

    # --- BM25 search (OpenSearch) ---
    t_start = time.time()
    try:
        res = client.search(index=TRIALS_INDEX_NAME, body=body)
    except Exception as e:
        logger.exception("OpenSearch query failed")
        raise HTTPException(status_code=500, detail=str(e))
    
    t_os = time.time()
    logger.info(f"OpenSearch Query took: {t_os - t_start:.4f}s")

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
            conditions_cuis=src.get("conditions_cuis") or [],
            study_type=src.get("study_type"),
            locations=loc_strings,
            score=score,  # temporarily BM25 score
            retrieval_score_raw=score,
            eligibility_criteria_raw=src.get("eligibility_criteria_raw"),
            parsed_criteria=src.get("parsed_criteria"),
            min_age_years=src.get("min_age_years"),
            max_age_years=src.get("max_age_years"),
            sex=src.get("sex")
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

    # --- Dense retrieval (FAISS) + hybrid fusion (RRF) ---
    if q and vector_search.ready and hits:
        # 1. Get BM25 Ranks (hits are already sorted by BM25 score from OpenSearch)
        bm25_ranked_ids = [h.nct_id for h in hits]

        # 2. Get Dense Ranks
        # Use a reasonably large k for dense candidates
        dense_results = vector_search.search(q, k=max(total_candidates * 3, total_candidates))
        dense_ranked_ids = [nct_id for (nct_id, _) in dense_results]

        # 3. Compute RRF
        # We fuse two lists: BM25 results and Dense results
        rrf_scores = compute_rrf([bm25_ranked_ids, dense_ranked_ids], k=60)

        # 4. Assign RRF scores to hits
        # Note: We only keep hits that were returned by BM25 (OpenSearch) to respect filters (Age, Gender, etc.)
        # If a doc is in Dense but not BM25, it's currently dropped because we filter by OpenSearch first.
        # Ideally, we would union the sets, but for now we re-score the filtered BM25 hits.
        for hit in hits:
            hit.score = rrf_scores.get(hit.nct_id, 0.0)
            # We can still keep the raw retrieval score for debugging if needed
            
        # sort by RRF score desc
        hits.sort(key=lambda h: h.score, reverse=True)

    # Optional feasibility scoring + blending
    if patient_profile:
        t_feas_start = time.time()
        _apply_feasibility_rerank(
            hits=hits,
            criteria_by_id=criteria_by_id,
            patient_profile=patient_profile,
            feasibility_weight=feasibility_weight,
        )
        t_feas_end = time.time()
        logger.info(f"Feasibility Rerank took: {t_feas_end - t_feas_start:.4f}s")

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
            "overall_status", "conditions", "conditions_cuis", "study_type", "locations",
            "criteria_inclusion", "criteria_exclusion", "eligibility_criteria_raw",
            "parsed_criteria",
            "min_age_years",
            "max_age_years",
            "sex",
            "healthy_volunteers",
            "enrollment"
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
                conditions_cuis=src.get("conditions_cuis") or [],
                study_type=src.get("study_type"),
                locations=locations,
                score=score,
                retrieval_score_raw=raw_dense,
                eligibility_criteria_raw=src.get("eligibility_criteria_raw"),
                parsed_criteria=src.get("parsed_criteria"),
                min_age_years=src.get("min_age_years"),
                max_age_years=src.get("max_age_years"),
                sex=src.get("sex")
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
# DB fetch helpers
# -----------------------------
def _fetch_trial_detail_from_db(nct_id: str) -> TrialDetail:
    conn = None
    try:
        conn = psycopg2.connect(POSTGRES_DSN)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    nct_id,
                    brief_title,
                    official_title,
                    brief_summary,
                    detailed_description,
                    conditions,
                    interventions,
                    study_type,
                    phase,
                    overall_status,
                    min_age_years,
                    max_age_years,
                    sex,
                    healthy_volunteers,
                    enrollment_actual,
                    enrollment_target,
                    start_date,
                    primary_completion_date,
                    completion_date,
                    last_updated,
                    eligibility_criteria_raw
                FROM trials
                WHERE nct_id = %s;
                """,
                (nct_id,),
            )
            trial_row = cur.fetchone()
            if not trial_row:
                raise HTTPException(status_code=404, detail="Trial not found")

            trial_id = trial_row["id"]

            cur.execute(
                """
                SELECT facility_name, city, state, country
                FROM sites
                WHERE trial_id = %s;
                """,
                (trial_id,),
            )
            sites_rows = list(cur.fetchall() or [])

            cur.execute(
                """
                SELECT type, text
                FROM criteria
                WHERE trial_id = %s
                ORDER BY sequence_no;
                """,
                (trial_id,),
            )
            criteria_rows = list(cur.fetchall() or [])
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Database error while fetching trial %s", nct_id)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()

    inclusion_blocks = [c.get("text", "") for c in criteria_rows if c.get("type") == "inclusion"]
    exclusion_blocks = [c.get("text", "") for c in criteria_rows if c.get("type") == "exclusion"]

    locations: List[TrialLocation] = []
    for s in sites_rows:
        locations.append(
            TrialLocation(
                facility_name=s.get("facility_name"),
                city=s.get("city"),
                state=s.get("state"),
                country=s.get("country"),
            )
        )

    title = trial_row.get("brief_title") or trial_row.get("official_title")
    # Normalize date/datetime objects from psycopg to strings for the response model
    def _to_iso(val):
        return val.isoformat() if hasattr(val, "isoformat") else val

    return TrialDetail(
        nct_id=trial_row.get("nct_id"),
        title=title,
        official_title=trial_row.get("official_title"),
        brief_summary=trial_row.get("brief_summary"),
        detailed_description=trial_row.get("detailed_description"),
        conditions=trial_row.get("conditions") or [],
        interventions=trial_row.get("interventions") or [],
        study_type=trial_row.get("study_type"),
        phase=trial_row.get("phase"),
        overall_status=trial_row.get("overall_status"),
        min_age_years=trial_row.get("min_age_years"),
        max_age_years=trial_row.get("max_age_years"),
        sex=trial_row.get("sex"),
        healthy_volunteers=trial_row.get("healthy_volunteers"),
        enrollment_actual=trial_row.get("enrollment_actual"),
        enrollment_target=trial_row.get("enrollment_target"),
        start_date=_to_iso(trial_row.get("start_date")),
        primary_completion_date=_to_iso(trial_row.get("primary_completion_date")),
        completion_date=_to_iso(trial_row.get("completion_date")),
        last_updated=_to_iso(trial_row.get("last_updated")),
        locations=locations,
        criteria_inclusion=" \n ".join([t for t in inclusion_blocks if t]) if inclusion_blocks else None,
        criteria_exclusion=" \n ".join([t for t in exclusion_blocks if t]) if exclusion_blocks else None,
        eligibility_criteria_raw=trial_row.get("eligibility_criteria_raw"),
    )


# -----------------------------
# Routes
# -----------------------------
@app.get("/trials/{nct_id}", response_model=TrialDetail, tags=["search"])
def get_trial_details(nct_id: str):
    """
    Fetch a single trial document by NCT ID directly from Postgres.
    """
    return _fetch_trial_detail_from_db(nct_id)


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
    required_pool = page * size
    candidate_size = max(required_pool, 50)
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
        candidate_size=candidate_size,  # for /search, candidate pool = requested page size
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

    import time
    t0 = time.time()
    
    normalized_conditions = []
    normalized_biomarkers = []
    if body.profile.conditions:
        try:
            normalizer = get_condition_normalizer()
            normalized_conditions = normalizer.normalize_list(body.profile.conditions)
        except Exception as e:
            logger.warning(f"Condition normalization failed: {e}, using original conditions")
            normalized_conditions = body.profile.conditions

    # Normalize biomarkers for feasibility scoring (keep originals for BM25 text)
    if body.profile.biomarkers:
        try:
            bnorm = get_biomarker_normalizer()
            normalized_biomarkers = bnorm.normalize_list(body.profile.biomarkers)
        except Exception as e:
            logger.warning(f"Biomarker normalization failed: {e}, using original biomarkers")
            normalized_biomarkers = body.profile.biomarkers

    
    q_text = build_profile_query_text(body.profile)
    # small query expansion with synonyms to boost BM25 recall
    # DISABLED: Causing query drift and recall drop
    # if normalized_conditions:
    #     extra_terms = _expand_condition_synonyms_for_query(normalized_conditions)
    #     if extra_terms:
    #         q_text = f"{q_text}. Related terms: " + ", ".join(extra_terms)
    
    
    if normalized_conditions:
        body.profile.conditions = normalized_conditions
    if normalized_biomarkers:
        body.profile.biomarkers = normalized_biomarkers

    # Always search over a candidate pool of 1000 docs for /rank,
    # but only return the top 20 to clients.
    candidate_size = 10000
    page = 1
    size = 20

    t1 = time.time()
    logger.info(f"Normalization & Setup took: {t1-t0:.4f}s")

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
