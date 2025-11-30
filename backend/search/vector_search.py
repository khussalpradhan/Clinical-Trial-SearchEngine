# backend/search/vector_search.py
"""
Runtime helper for dense retrieval over trials using a FAISS index
built by `backend.search.build_faiss_index`.
"""

import json
import os
from functools import lru_cache
from typing import List, Tuple

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from backend.config import (
    EMBEDDING_MODEL_NAME,
    FAISS_INDEX_PATH,
    FAISS_META_PATH,
)


class VectorSearch:
    def __init__(self) -> None:
        self._index: faiss.Index | None = None
        self._nct_ids: List[str] = []
        self._model: SentenceTransformer | None = None
        self._loaded: bool = False

    def _load(self) -> None:
        if self._loaded:
            return

        if not (os.path.exists(FAISS_INDEX_PATH) and os.path.exists(FAISS_META_PATH)):
            # Index not built yet; leave in "not ready" mode.
            self._loaded = True
            return

        self._index = faiss.read_index(FAISS_INDEX_PATH)

        with open(FAISS_META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self._nct_ids = meta["nct_ids"]
        
        
        model_name = meta.get("model_name", EMBEDDING_MODEL_NAME)
        
        if "S-PubMedBert-MS-MARCO" not in model_name:
            model_name = "pritamdeka/S-PubMedBert-MS-MARCO"
        
        self._model = SentenceTransformer(model_name)
        self._loaded = True

    @property
    def ready(self) -> bool:
        self._load()
        return (
            self._index is not None
            and self._model is not None
            and bool(self._nct_ids)
        )

    def _encode(self, text: str) -> np.ndarray:
        self._load()
        if not self.ready:
            raise RuntimeError("FAISS index / embedding model not ready")
        emb = self._model.encode(
            [text],
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32")
        faiss.normalize_L2(emb)
        return emb

    def search(self, query: str, k: int = 50) -> List[Tuple[str, float]]:
        """
        Return a list of (nct_id, dense_score) by decreasing dense_score.
        If the index is not ready, returns [].
        """
        if not query:
            return []
        if not self.ready:
            return []

        q_emb = self._encode(query)
        scores, indices = self._index.search(q_emb, k)
        idxs = indices[0]
        scs = scores[0]

        results: List[Tuple[str, float]] = []
        for idx, score in zip(idxs, scs):
            if idx < 0 or idx >= len(self._nct_ids):
                continue
            nct_id = self._nct_ids[idx]
            results.append((nct_id, float(score)))
        return results


@lru_cache(maxsize=1)
def get_vector_search() -> VectorSearch:
    # lru_cache makes this effectively a singleton in the process
    return VectorSearch()
