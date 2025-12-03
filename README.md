# Clinical Trial Search Engine

A high-performance hybrid search engine for clinical trials that combines **BM25** (keyword-based), **PubMedBERT** (dense vector search), and **Reciprocal Rank Fusion (RRF)**, enhanced by an **AI-powered Feasibility Scorer**. Designed to match patient profiles with relevant trials with < 2s latency.

---

## Key Features

- **Hybrid Search Architecture**: Combines BM25 and Dense Retrieval (S-PubMedBERT-MS-MARCO) using Reciprocal Rank Fusion (RRF) for robust ranking.
- **Smart Feasibility Scoring**:
  - **Cached Parsing**: Pre-parsed eligibility criteria stored in JSONB for millisecond-level access.
  - **Rule-Based Logic**: Deterministic scoring for Age, Gender, Conditions, Biomarkers, and Lab Values.
  - **Hard Exclusions**: Instantly filters out trials with absolute contraindications (e.g., Pregnancy, HIV).
- **High Performance**:
  - **Latency**: < 2 seconds per complex query (down from 60s+).
  - **Scale**: Searches over 580,000+ trials.
  - **Candidate Pool**: Re-ranks top 10,000 candidates for maximum recall.
- **Modern Tech Stack**: FastAPI, PostgreSQL (JSONB + GIN Index), OpenSearch, Docker Compose.

---

## Architecture

1.  **Retrieval Layer**:
    *   **Keyword**: OpenSearch (BM25) with field boosting (Title^3, Conditions^2).
    *   **Semantic**: FAISS (Dense Vectors) using `pritamdeka/S-PubMedBert-MS-MARCO`.
    *   **Fusion**: RRF (`1 / (k + rank)`) merges results from both streams.

2.  **Feasibility Layer**:
    *   **Criteria Parser**: Offline NLP pipeline parses unstructured text into structured JSON (Age, Gender, Inclusion/Exclusion lists).
    *   **Caching**: Parsed data stored in PostgreSQL `parsed_criteria` column.
    *   **Scorer**: Real-time comparison of Patient Profile vs. Trial Criteria.

3.  **Infrastructure**:
    *   **Backend**: Python 3.11 (FastAPI).
    *   **Database**: PostgreSQL 16.
    *   **Search Engine**: OpenSearch 2.15.

---

## Evaluation Metrics

Performance on **TREC 2021 Clinical Trials** dataset (Top-20 Retrieval):

| Metric | Score | Interpretation |
| :--- | :--- | :--- |
| **MRR@10** | **0.48** | First relevant result appears at position ~2 on average. |
| **Hit Rate@10** | **70%** | 70% of queries find a relevant trial in the top 10. |
| **NDCG@10** | **0.21** | Strong ranking quality for top results. |
| **Precision@1** | **35%** | The very first result is relevant 35% of the time. |

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- 20 GB+ RAM (for Vector Index)

### 1. Clone & Start Services
```bash
git clone <repo_url>
cd ClinicalTrialSearchEngine

# Start all services (Backend, Frontend, DB, OpenSearch)
docker compose up -d --build
```

### 2. Database Setup (First Time UsersOnly)
If you are setting this up from scratch, you need to initialize the DB and ingest data.

```bash
# 1. Create Tables
docker exec ctf_backend python3 -m backend.db.init_db

# 2. Add Parsed Criteria Schema
docker exec ctf_backend python3 -m backend.db.add_column

# 3. Ingest Data (Takes ~2-3 hours for full 580k dataset)
docker exec -d ctf_backend python3 -m backend.db.scrape_clinical_trials --max-studies 600000
```

### Fast Setup (Using Team Data Dump)
#### Follow the below steps till step 4 for complete setup.
---
**1. Vector Indexing (FAISS)** 

Move the FAISS index dump to the `backend/data` directory.

**2. Restore the Postgres Dump:**
```bash
# Ensure DB container is running
docker compose up -d postgres

# Drop existing DB (if any) and recreate
docker exec ctf_postgres dropdb -U clinical_user clinical_trials
docker exec ctf_postgres createdb -U clinical_user clinical_trials

# Restore data (unzip on the fly)
gunzip -c clinical_trials_dump.sql.gz | docker exec -i ctf_postgres psql -U clinical_user -d clinical_trials
```
**3. Build Search Indexes:**
```bash
# 1. Build OpenSearch Index
docker exec ctf_backend python3 -m backend.search.init_index
docker exec ctf_backend python3 -m backend.search.reindex_from_postgres
```

**4. Final Step:**
```bash
# Build Docker 
docker compose down
docker compose up -d --build
```
---

### 3. Build Search Indexes (First Time UsersOnly)
**Required Step**: Sync the restored database with the search engine and build the vector index.

```bash
# 1. Build OpenSearch Index
docker exec ctf_backend python3 -m backend.search.init_index
docker exec ctf_backend python3 -m backend.search.reindex_from_postgres

# 2. Build FAISS Index (Vector Search)
docker exec ctf_backend python3 -m backend.search.build_faiss_index
```

*(Note: The data dump contains the parsed criteria and CUIs, so you do **not** need to run the migration scripts, but you **DO** need to build the indexes.)*

### 4. Access the App
*   **Frontend**: [http://localhost:8501](http://localhost:8501)
*   **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## API Endpoints

### `POST /rank`
Main search endpoint. Accepts a patient profile and returns ranked trials.

**Request:**
```json
{
  "patient_profile": {
    "age": 65,
    "gender": "Female",
    "conditions": ["Breast Cancer"],
    "biomarkers": ["HER2+", "ER+"],
    "ecog": 1
  },
  "bm25_weight": 0.5,
  "feasibility_weight": 0.6
}
```

### `GET /trials/{nct_id}`
Get full details for a specific trial, including the parsed eligibility criteria.

---

## Development

### Hot Reloading
The `backend` and `frontend` services are mounted with hot-reloading enabled.
*   Edit files in `./backend` -> API restarts automatically.
*   Edit files in `./frontend` -> Streamlit updates instantly.

### Running Evaluation
To reproduce the metrics:
```bash
docker exec ctf_backend python3 -m backend.evaluation.evaluation_pipeline
```

---

## Project Structure

```
.
├── backend/
│   ├── api/            # FastAPI Main Application
│   ├── db/             # Database Migrations & Scrapers
│   ├── evaluation/     # TREC Evaluation Pipeline
│   ├── nlp/            # Feasibility Scorer & Criteria Parser
│   └── search/         # OpenSearch & FAISS Logic
├── frontend/           # Streamlit UI
├── data/               # Persistent Data (GitIgnored)
└── docker-compose.yml  # Infrastructure Orchestration
```

---

## Contributors
- Khussal
- Shashank
- Kritika
- Aastha
