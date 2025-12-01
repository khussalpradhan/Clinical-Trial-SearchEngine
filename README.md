# Clinical Trial Search Engine

A hybrid search engine for clinical trials combining BM25 (keyword-based), dense vector search (FAISS), and AI-powered feasibility scoring. Designed for researchers and healthcare professionals to match patient profiles with relevant trials.

---

## Features

- **Hybrid Search**: BM25 + FAISS dense retrieval for accurate, relevant results
- **Inclusion-Only Scoring**: Both BM25 and FAISS use only inclusion criteria (not exclusion) for better matching
- **AI Feasibility Scoring**: NLP-powered analysis of patient eligibility against trial criteria
- **Configurable Weights**: Tune BM25/FAISS balance and feasibility scoring via API
- **550K+ Trials**: Full ClinicalTrials.gov dataset support
- **RESTful API**: FastAPI-powered backend with comprehensive endpoints

---

## Architecture

- **Backend**: Python (FastAPI)
- **Search**: OpenSearch (BM25), FAISS (dense vectors)
- **Embeddings**: `pritamdeka/S-PubMedBert-MS-MARCO` (medical-domain optimized)
- **Database**: PostgreSQL
- **NLP**: Custom criteria parser with biomarker/condition normalization

---

## Quick Start

### Prerequisites

- Python 3.11.9
- Docker & Docker Compose
- 16GB+ RAM recommended (for FAISS index building)

### 1. Setup Python Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 2. Start Services (Postgres + OpenSearch)

```bash
docker-compose up -d
```

### 3. Initialize Database

```bash
python -m backend.db.init_db
```

### 4. Ingest Clinical Trials Data

```bash
# Full dataset (550K+ trials, ~2-3 hours)
python -m backend.db.scrape_clinical_trials --max-studies 600000

# Quick test (1000 trials, ~2 minutes)
python -m backend.db.scrape_clinical_trials --max-studies 1000
```

### 5. Build Search Indexes

```bash
# Create OpenSearch index
python -m backend.search.init_index

# Populate OpenSearch from Postgres
python -m backend.search.reindex_from_postgres --chunk-size 1000

# Build FAISS vector index (memory-intensive, may take time)
python -m backend.search.build_faiss_index
```

### 6. Start API Server (Docker)

```bash
# Ensure services are up
docker compose up -d --build

# Start or restart backend API inside the container
docker compose up -d backend

# Health check
curl http://localhost:8000/health
```

API available at: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

---

## API Endpoints

### Rank Trials (with Patient Profile)
```bash
POST /rank
```

```json
{
  "patient_profile": {
    "age": 65,
    "gender": "Female",
    "conditions": [
      "Non-small cell lung cancer",
      "Breast Cancer",
      "Heart Failure",
      "Chronic Kidney Disease",
      "Respiratory Failure",
      "Liver Failure",
      "Leukemia",
      "Prostate Cancer",
      "Skin Cancer",
      "Cervical Cancer",
      "Bone Cancer"
    ],
    "ecog": 1,
    "biomarkers": [
      "EGFR",
      "HER2",
      "ALK",
      "KRAS",
      "BRAF",
      "BCR-ABL",
      "FLT3",
      "CD19",
      "ER",
      "PR"
    ],
    "history": [
      "History_MI",
      "History_Stroke",
      "Autoimmune_Disease",
      "Prior_Malignancy",
      "HIV",
      "Hepatitis",
      "Pregnancy"
    ],
    "labs": {
      "Creatinine": 1.2,
      "GFR": 55.0,
      "Bilirubin": 0.8,
      "AST": 35.0,
      "ALT": 40.0,
      "INR": 1.1,
      "PSA": 4.5,
      "Testosterone": 300.0,
      "BNP": 150.0,
      "LVEF": 50.0,
      "Platelet_Count": 150,
      "Hemoglobin": 11.5,
      "ANC": 2500
    },
    "prior_lines": 2,
    "days_since_last_treatment": 45
  }
}
```



### Get Trial Details
```bash
GET /trials/{nct_id}
```

---

## Configuration

### Weights (User-Configurable)

- **`bm25_weight`** (0.0-1.0, default: 0.5): Balance between BM25 and FAISS scores
  - 1.0 = pure BM25 (keyword)
  - 0.0 = pure FAISS (semantic)
  
- **`feasibility_weight`** (0.0-1.0, default: 0.6): Balance between retrieval and feasibility scores
  - 1.0 = pure feasibility (NLP eligibility matching)
  - 0.0 = pure retrieval (BM25 + FAISS)

### BM25 Field Weights

- `title^3` — 3x boost
- `conditions^2` — 2x boost
- `brief_summary^2` — 2x boost
- `criteria_inclusion_clean^2` — 2x boost (inclusion-only)
- `interventions`, `detailed_description` — 1x

### FAISS Document Weights

- Conditions: 3x repetition (highest signal)
- Interventions: 2x repetition
- Inclusion criteria: extracted via regex (exclusion removed)
- Demographics, summaries: 1x

### Feasibility Scoring Summary

- Condition match: +40
- Biomarker match: +25
- ECOG allowed: +15
- Lines of therapy within range: +10
- Age in range: +5
- Gender match or All: +5
- Washout cleared: +5
- Lab thresholds: +5 per passed lab (capped at +15 total); failing key labs marks trial infeasible
- Hard exclusions (e.g., Pregnancy, CNS Mets, HIV, Hepatitis): score = 0 and infeasible

Final score is capped at 100. Infeasible trials receive 0.

### Final Scoring and Normalization

- Hybrid retrieval scoring (BM25 + Dense):
  - Normalize BM25 scores across candidates to `[0,1]`.
  - Normalize dense (FAISS) scores across candidates to `[0,1]`.
  - Combine via `hybrid = bm25_weight * bm25_norm + (1 - bm25_weight) * dense_norm`.
- Feasibility blending (applied after retrieval):
  - Normalize retrieval scores to `[0,1]` again (per page’s candidate set).
  - Convert feasibility scores (0–100) to `[0,1]` by `feas_norm = feasibility_score / 100`.
  - Final displayed score per trial:
    - `final = (1 - feasibility_weight) * retrieval_norm + feasibility_weight * feasi_norm`.
  - Trials marked infeasible keep feasibility score `0`; final score reflects the blend.
  - Candidates are sorted by `final` descending; pagination is applied after blending.


---

## Data Sharing (For Teams)

The `data/` folder (FAISS indexes, artifacts) is `.gitignore`d due to size (>1.6GB). To share with teammates:

1. **Compressed archive**: `data_YYYYMMDD.tar.gz` (generated via `tar -czf`)
2. **Download & extract**:
   ```bash
   tar -xzf data_YYYYMMDD.tar.gz -C .
   ```
3. **Verify checksum** (optional):
   ```bash
   shasum -a 256 -c data_YYYYMMDD.tar.gz.sha256
   ```

Alternatively, teammates can rebuild indexes from scratch (steps 4-5 above).

---

## Development

### Run Tests
```bash
pytest backend/tests
```

### Code Quality
```bash
# Format
black backend/

# Lint
flake8 backend/
```

### Rebuild Indexes (After Code Changes)
```bash
# OpenSearch only
python -m backend.search.init_index
python -m backend.search.reindex_from_postgres

# FAISS only
python -m backend.search.build_faiss_index
```

---

## Project Structure

```
ClinicalTrialSearchEngine/
├── backend/
│   ├── api/              # FastAPI endpoints
│   ├── db/               # Postgres schema, ingestion
│   ├── search/           # OpenSearch, FAISS, reindexing
│   ├── nlp/              # Feasibility scorer, parsers
│   └── config.py         # Environment config
├── data/                 # FAISS indexes (local, not committed)
├── docker-compose.yml    # Postgres + OpenSearch containers
├── Dockerfile            # (Optional) Containerized backend
└── README.md
```

---

## Troubleshooting

### FAISS Build Slow or OOM
- Reduce `batch_size` in `build_faiss_index.py` (default: 64)
- Run outside Docker for faster CPU/RAM access
- Downsample trials for testing

### OpenSearch Not Responding
```bash
docker-compose restart opensearch
curl -X GET "http://localhost:9200/_cluster/health"
```

### Postgres Connection Error
```bash
docker-compose restart postgres
# Check logs
docker-compose logs postgres
```

### Push Rejected (Large Files)
Already handled via `.gitignore` for `data/`. If history contains large files, see commit history cleanup guide.

---

## License

MIT (or your preferred license)

---

## Contributors

- Khussal
- Shashank
- Kritika 
- Aastha

---

## Acknowledgments

- **ClinicalTrials.gov** for open clinical trial data
- **PubMedBERT** for medical-domain embeddings
- **OpenSearch**, **FAISS**, **FastAPI** communities
