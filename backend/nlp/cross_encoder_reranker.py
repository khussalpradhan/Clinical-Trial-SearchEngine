# backend/nlp/cross_encoder_reranker.py

import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder as _CrossEncoderType

logger = logging.getLogger(__name__)

# MS-MARCO cross-encoder: trained for passage relevance ranking, fast on CPU (22M params).
# Swap for a fine-tuned biomedical cross-encoder when one becomes available.
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Maximum token budget shared between query and document.
# ms-marco-MiniLM models support 512; keep headroom for special tokens.
MAX_LENGTH = 512


class CrossEncoderReranker:
    """
    Final-stage deep interaction re-ranker using a Cross-Encoder.

    Unlike the bi-encoder (FAISS), the Cross-Encoder concatenates the patient
    profile query and the trial document as a single sequence and runs full
    self-attention over both, enabling token-level interaction:

      Score(q, d) = σ(W · Transformer([CLS] q [SEP] d) + b)

    This captures:
    - Negation: "no prior immunotherapy" vs "prior immunotherapy"
    - Numerical reasoning: "Age ≥ 18", "Creatinine ≤ 1.5 mg/dL"
    - Contextual biomarker weighting: EGFR / HER2 / ALK prioritisation

    Usage:
        reranker = CrossEncoderReranker()
        reranker.rerank(query_text, hits, criteria_by_id, top_n=50, weight=0.3)
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, max_length: int = MAX_LENGTH):
        self.model_name = model_name
        self.max_length = max_length
        self._model: Optional["_CrossEncoderType"] = None
        self._load_attempted = False

    # ------------------------------------------------------------------
    # Lazy loading — mirrors FeasibilityScorer._get_umls() pattern
    # ------------------------------------------------------------------

    def _get_model(self) -> Optional["_CrossEncoderType"]:
        if not self._load_attempted:
            self._load_attempted = True
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(
                    self.model_name,
                    max_length=self.max_length,
                    device="cpu",  # CPU-only to match existing FAISS/bi-encoder setup
                )
                logger.info("Cross-Encoder loaded: %s", self.model_name)
            except Exception as exc:
                logger.warning("Failed to load Cross-Encoder (%s): %s", self.model_name, exc)
                self._model = None
        return self._model

    @property
    def ready(self) -> bool:
        return self._get_model() is not None

    # ------------------------------------------------------------------
    # Document formatting
    # ------------------------------------------------------------------

    def _format_trial_text(
        self,
        title: Optional[str],
        brief_summary: Optional[str],
        criteria_text: str,
    ) -> str:
        """
        Assemble the trial-side document fed to the cross-encoder.

        Token budget split (within MAX_LENGTH shared with query):
          - title: up to ~20 tokens — high signal, keep whole
          - brief_summary: first 300 chars — context
          - criteria_text: first 400 chars — eligibility details (most relevant)
        """
        parts: List[str] = []
        if title:
            parts.append(title.strip())
        if brief_summary:
            parts.append(brief_summary.strip()[:300])
        if criteria_text:
            parts.append(criteria_text.strip()[:400])
        return " | ".join(parts)

    # ------------------------------------------------------------------
    # Core rerank method
    # ------------------------------------------------------------------

    def rerank(
        self,
        query_text: str,
        hits: list,
        criteria_by_id: dict,
        top_n: int = 100,
        weight: float = 0.3,
    ) -> None:
        """
        Re-rank *hits* in-place using cross-encoder scores.

        Only the leading ``top_n`` hits are re-scored (they are already ordered
        by the upstream retrieval + feasibility blend, so processing the tail
        yields diminishing returns while keeping latency bounded).

        The cross-encoder score is min-max normalised to [0, 1] and then
        blended with the existing hit score:

            final = (1 - weight) * existing_score + weight * ce_norm

        Args:
            query_text:     Patient profile or free-text query string.
            hits:           List of TrialHit objects, sorted descending by score.
            criteria_by_id: Dict mapping nct_id -> eligibility criteria text.
            top_n:          Number of leading hits to re-score (default 50).
            weight:         Cross-encoder blend weight in [0, 1] (default 0.3).
        """
        model = self._get_model()
        if not model or not hits or not query_text.strip():
            return

        candidates = hits[:top_n]

        # Build (query, document) pairs for batch inference
        pairs: List[tuple] = []
        for hit in candidates:
            criteria_text = criteria_by_id.get(hit.nct_id, "")
            doc_text = self._format_trial_text(
                hit.title,
                hit.brief_summary,
                criteria_text,
            )
            pairs.append((query_text, doc_text))

        try:
            ce_scores = model.predict(pairs, show_progress_bar=False)
        except Exception as exc:
            logger.exception("Cross-Encoder inference failed: %s", exc)
            return

        # Min-max normalise to [0, 1]
        if len(ce_scores) == 0:
            return
        min_s = float(min(ce_scores))
        max_s = float(max(ce_scores))
        if max_s > min_s:
            ce_norm = [(float(s) - min_s) / (max_s - min_s) for s in ce_scores]
        else:
            ce_norm = [1.0] * len(ce_scores)

        # Blend with existing score and update hits
        for hit, norm_score in zip(candidates, ce_norm):
            existing = hit.score if hit.score is not None else 0.0
            hit.score = (1.0 - weight) * existing + weight * norm_score

        # Re-sort the re-scored window and write back into the original list
        candidates.sort(key=lambda h: h.score, reverse=True)
        hits[:top_n] = candidates
