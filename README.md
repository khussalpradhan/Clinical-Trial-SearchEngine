# Clinical Trial Search Engine

A high-performance hybrid search engine for clinical trials that combines **BM25** (keyword-based), **PubMedBERT** (dense vector search), and **Reciprocal Rank Fusion (RRF)**, enhanced by an **AI-powered Feasibility Scorer**. Designed to match patient profiles with relevant trials with < 2s latency.

---

## Key Features

- **Multi-Stage Hybrid Architecture**: Combines BM25 and Dense Retrieval (S-PubMedBERT-MS-MARCO) using Reciprocal Rank Fusion (RRF) for robust ranking.
- **Smart Feasibility Scoring**:
  - **Cached Parsing**: Pre-parsed eligibility criteria stored in JSONB for millisecond-level access.
  - **Rule-Based Logic**: Deterministic scoring for Age, Gender, Conditions, Biomarkers, and Lab Values.
  - **Hard Exclusions**: Instantly filters out trials with absolute contraindications.
- **Deep Re-ranking**: Uses a Cross-Encoder (`ms-marco-MiniLM-L-6-v2`) to apply deep self-attention between the query and trial document for unparalleled precision on the top 100 candidates.
- **High Performance**:
  - **Latency**: < 2 seconds per complex query.
  - **Scale**: Searches over 580,000+ trials.
- **Modern Tech Stack**: FastAPI, PostgreSQL (JSONB + GIN Index), OpenSearch, Docker Compose.

---

## Architecture

Our search pipeline processes queries through three increasingly sophisticated layers:

1.  **Stage 1: Retrieval (Candidate Generation)**:
    *   **Keyword Filtering**: OpenSearch (BM25) with field boosting (Title^3, Conditions^2) fetches the top 500 candidates while enforcing hard age and gender filters.
    *   **Semantic Matching**: FAISS (Dense Vectors) uses `pritamdeka/S-PubMedBert-MS-MARCO` to catch semantic similarities.
    *   **Fusion**: RRF (`1 / (k + rank)`) merges results from both streams to produce highly robust candidate rankings.

2.  **Stage 2: Feasibility Layer (Zero-Shot Elimination)**:
    *   **NLP Scorer**: An intelligent Scispacy + UMLS pipeline "reads" the trial's Inclusion/Exclusion criteria and measures compatibility against the patient profile (age, biomarkers, conditions).
    *   **Elimination**: Trials explicitly contradicting patient state are thrown out; valid trials receive a 0-100 logic score blended into the retrieval ranking.

3.  **Stage 3: Deep Re-Ranking (Cross-Encoder)**:
    *   **Self-Attention**: The top 100 trials from Stage 2 are concatenated with the query and fed side-by-side into a Cross-Encoder transformer.
    *   **Precision**: Nuances like numerical boundaries and complex medical phrasing are heavily factored to perfectly sort the final top results.

4.  **Infrastructure**:
    *   **Backend**: Python 3.11 (FastAPI).
    *   **Database**: PostgreSQL 16.
    *   **Search Engine**: OpenSearch 2.15.

---

## Evaluation Metrics

Performance on **TREC 2021 Clinical Trials** dataset. Our pipeline uses a 100-document Cross-Encoder re-ranking limit:

| Metric | Score | Interpretation |
| :--- | :--- | :--- |
| **MRR@10** | **0.52** | First highly relevant result appears at position ~2 on average. |
| **Precision@1** | **44%** | The absolute #1 returned result is critically relevant 44% of the time (a massive boost from our 35% baseline). |
| **Hit Rate@10** | **69%** | ~69% of queries find at least one relevant trial in the very first page of results. |
| **NDCG@5** | **0.26** | Measures deep ranking quality for the top 5 results, optimized by the Cross-Encoder. |

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

**Option A (Inside Docker - Recommended)**  
Run the pipeline directly within your live Linux environment to bypass host-machine memory limits:
```bash
docker exec -it ctf_backend python -m backend.evaluation.evaluation_pipeline
```

**Option B (Local Mac Execution via Endpoint)**  
Because allocating all three NLP models natively on Apple Silicon may cause `mps` GPU driver crashes or OpenMP threading collisions, we recommend avoiding loading the models natively. Ensure your Docker backend is running, then run locally utilizing the environment flags to prevent crashes:
```bash
OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE python3 -m backend.evaluation.evaluation_pipeline
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
