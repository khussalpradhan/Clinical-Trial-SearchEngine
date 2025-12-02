# RRF Parameter Tuning Log

## Baseline (Before RRF)
- MRR@10: 0.255
- NDCG@10: 0.090
- Recall@100: 0.015

## Configuration 1: Initial RRF (FAILED)
**Parameters:**
- Candidate pool: 100
- RRF k: 60
- BM25 weight: 0.5

**Results:**
- MRR@10: 0.147 (-42% ❌)
- NDCG@10: 0.057 (-37% ❌)
- Recall@100: 0.007 (-53% ❌)

**Analysis:** Severe performance degradation. k=60 too high, candidate pool too small.

---

## Configuration 2: Tuned RRF (TESTING NOW)
**Parameters:**
- Candidate pool: **500** (5x increase)
- RRF k: **20** (reduced from 60)
- BM25 weight: 0.5

**Hypothesis:**
- Larger pool → more relevant docs available for fusion
- Lower k → prioritizes top-ranked results more
- Should improve recall and ranking quality

**Run command:**
```bash
python3 -m backend.evaluation.evaluation_pipeline
```

**Expected improvements:**
- Recall should increase (more candidates = more chances to find relevant docs)
- MRR/NDCG should improve (lower k emphasizes top results)

---

## Next Experiments (if needed):

### Config 3: Try k=10
- Even more aggressive top-heavy weighting

### Config 4: Try k=40  
- Middle ground between 20 and 60

### Config 5: Tune BM25 weight
- Try 0.3, 0.7 to adjust BM25 vs dense balance

### Config 6: Remove UMLS expansion
- Disable synonym expansion (lines 1010-1012 in main.py)
