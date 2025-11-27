# backend/search/build_faiss_index.py
"""
Utilities to generate MiniLM embeddings for all trials and build a FAISS index.

Usage (from project root):

    python -m backend.search.build_faiss_index

Make sure your database is populated (via /admin/scrape) before running.
"""

import json
import os
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
                    eligibility_criteria_raw
                FROM trials
                """
            )
            rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def _build_document_text(row: dict) -> str:
    parts: List[str] = [
        row.get("brief_title") or "",
        row.get("official_title") or "",
        row.get("brief_summary") or "",
        row.get("detailed_description") or "",
    ]

    conditions = row.get("conditions") or []
    if isinstance(conditions, list):
        parts.append("; ".join(conditions))
    elif conditions:
        parts.append(str(conditions))

    interventions = row.get("interventions") or []
    if isinstance(interventions, list):
        parts.append("; ".join(interventions))
    elif interventions:
        parts.append(str(interventions))

    criteria = row.get("eligibility_criteria_raw") or ""
    parts.append(criteria)

    text = ". ".join(p for p in parts if p)
    # normalize whitespace
    return " ".join(text.split())


def build_faiss_index(batch_size: int = 128) -> None:
    print("Loading trials from Postgres...", flush=True)
    rows = _fetch_trials()
    if not rows:
        print("No trials found in database.", flush=True)
        return

    print(f"Loaded {len(rows)} trials.", flush=True)
    print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}", flush=True)
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    dim = model.get_sentence_embedding_dimension()
    print(f"Embedding dimension: {dim}", flush=True)

    texts: List[str] = []
    nct_ids: List[str] = []
    for row in rows:
        doc_text = _build_document_text(row)
        if not doc_text:
            continue
        nct_ids.append(row["nct_id"])
        texts.append(doc_text)

    total = len(texts)
    print(f"Building embeddings for {total} trials (streaming in batches)...", flush=True)

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
        "model_name": EMBEDDING_MODEL_NAME,
    }
    _ensure_dir(FAISS_META_PATH)
    with open(FAISS_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f)

    print(f"Wrote metadata to {FAISS_META_PATH}", flush=True)
    print("✅ FAISS build done.", flush=True)



if __name__ == "__main__":
    build_faiss_index()
