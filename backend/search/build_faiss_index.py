# backend/search/build_faiss_index.py
"""
Utilities to generate embeddings for all trials and build a FAISS index.
Uses all-mpnet-base-v2 for better medical domain accuracy.

Usage (from project root):

    python -m backend.search.build_faiss_index

Make sure your database is populated (via /admin/scrape) before running.
"""

import json
import os
import re
from typing import List

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer
import faiss

from backend.config import (
    POSTGRES_DSN,
    EMBEDDING_MODEL_NAME,
    FAISS_INDEX_PATH,
    FAISS_META_PATH,
    EMBEDDINGS_DIR,
)


def _ensure_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _fetch_trials() -> List[dict]:
    conn = psycopg2.connect(POSTGRES_DSN)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    nct_id,
                    brief_title,
                    official_title,
                    brief_summary,
                    detailed_description,
                    conditions,
                    interventions,
                    eligibility_criteria_raw,
                    min_age_years,
                    max_age_years,
                    sex,
                    healthy_volunteers
                FROM trials
                """
            )
            rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def _build_document_text(row: dict) -> str:
  
    
    parts: List[str] = []
    
    # Titles - keep both
    title1 = row.get("brief_title") or ""
    title2 = row.get("official_title") or ""
    if title1:
        parts.append(title1)
    if title2 and title2 != title1:
        parts.append(title2)
    
    # Summary
    summary = row.get("brief_summary") or ""
    if summary:
        parts.append(summary)
    
    # Detailed description - truncate to avoid noise
    detailed = row.get("detailed_description") or ""
    if detailed:
        # Take first 500 chars to avoid overwhelming the embedding
        parts.append(detailed[:500])
    
    # CONDITIONS - BOOST 3x (most important for matching)
    conditions = row.get("conditions") or []
    if isinstance(conditions, list) and conditions:
        cond_text = "Conditions: " + ", ".join(conditions)
        # Repeat 3 times for boosting
        parts.extend([cond_text, cond_text, cond_text])
    elif conditions:
        cond_text = f"Conditions: {conditions}"
        parts.extend([cond_text, cond_text, cond_text])
    
    # INTERVENTIONS - BOOST 2x
    interventions = row.get("interventions") or []
    if isinstance(interventions, list) and interventions:
        int_text = "Interventions: " + ", ".join(interventions)
        parts.extend([int_text, int_text])
    elif interventions:
        int_text = f"Interventions: {interventions}"
        parts.extend([int_text, int_text])
    
    # Structured Demographics - natural language
    sex = row.get("sex")
    if sex and sex.upper() != "ALL":
        parts.append(f"Eligible sex: {sex}")
    
    min_age = row.get("min_age_years")
    max_age = row.get("max_age_years")
    if min_age is not None or max_age is not None:
        age_min = int(min_age) if min_age else 0
        age_max = int(max_age) if max_age else 120
        parts.append(f"Age range: {age_min} to {age_max} years")
    
    healthy = row.get("healthy_volunteers")
    if healthy:
        parts.append("Healthy volunteers accepted")
    
    # Eligibility Criteria - ONLY inclusion (smart split)
    raw_text = row.get("eligibility_criteria_raw") or ""
    inclusion_text = raw_text
    
    if raw_text:
       
        # Match "Exclusion Criteria:" or "EXCLUSION CRITERIA" with optional whitespace
        match = re.search(r'(?i)exclusion\s+criteria\s*:?', raw_text)
        if match:
            # Take everything before the exclusion section
            inclusion_text = raw_text[:match.start()].strip()
        
        # Also try to extract just "Inclusion Criteria" section if explicitly marked
        incl_match = re.search(r'(?i)inclusion\s+criteria\s*:?([\s\S]*?)(?=exclusion\s+criteria|$)', raw_text)
        if incl_match:
            inclusion_text = incl_match.group(1).strip()
        
        if inclusion_text:
            # Limit to 1000 chars to avoid overwhelming
            parts.append(inclusion_text[:1000])
    
    # Join with periods, clean extra whitespace
    text = ". ".join(p for p in parts if p.strip())
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def build_faiss_index(batch_size: int = 64) -> None:
    
    print("Loading trials from Postgres...", flush=True)
    rows = _fetch_trials()
    if not rows:
        print("No trials found in database.", flush=True)
        return

    print(f"Loaded {len(rows)} trials.", flush=True)
    
    
    model_name = "pritamdeka/S-PubMedBert-MS-MARCO"
    print(f"Loading BEST medical embedding model: {model_name}", flush=True)
    print("(Downloading PubMedBERT medical search model - optimized for clinical trials...)", flush=True)
    model = SentenceTransformer(model_name)
    dim = model.get_sentence_embedding_dimension()
    print(f"Embedding dimension: {dim} (medical-domain optimized)", flush=True)

    texts: List[str] = []
    nct_ids: List[str] = []
    skipped = 0
    
    for row in rows:
        doc_text = _build_document_text(row)
        # Skip trials with very little text (likely incomplete data)
        if not doc_text or len(doc_text.strip()) < 50:
            skipped += 1
            continue
        nct_ids.append(row["nct_id"])
        texts.append(doc_text)
    
    total = len(texts)
    if skipped > 0:
        print(f"Skipped {skipped} trials with insufficient text.", flush=True)
    print(f"Building embeddings for {total} trials (streaming in batches of {batch_size})...", flush=True)

    # Create FAISS index up front
    index = faiss.IndexFlatIP(dim)

    # Stream batches: encode -> normalize -> add to index
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = texts[start:end]

        print(f"Encoding batch {start}..{end} / {total}", flush=True)
        emb = model.encode(
            batch,
            batch_size=len(batch),
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32")

        # L2-normalize so inner product ≈ cosine similarity
        faiss.normalize_L2(emb)

        # Add directly to FAISS; no big vstack
        index.add(emb)

    print(f"FAISS index size: {index.ntotal} vectors", flush=True)

    _ensure_dir(FAISS_INDEX_PATH)
    faiss.write_index(index, FAISS_INDEX_PATH)
    print(f"Wrote FAISS index to {FAISS_INDEX_PATH}", flush=True)

    meta = {
        "nct_ids": nct_ids,
        "model_name": "pritamdeka/S-PubMedBert-MS-MARCO",
        "dimension": dim,
        "total_trials": total,
        "index_type": "FlatIP",
        "similarity_metric": "cosine",
    }
    _ensure_dir(FAISS_META_PATH)
    with open(FAISS_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Wrote metadata to {FAISS_META_PATH}", flush=True)
    print(f"FAISS build complete! Indexed {total} trials using S-PubMedBert-MS-MARCO.", flush=True)
    print(f" Index path: {FAISS_INDEX_PATH}", flush=True)
    print(f" Model: S-PubMedBert-MS-MARCO (medical search optimized, SOTA for clinical text)", flush=True)



if __name__ == "__main__":
    build_faiss_index()
