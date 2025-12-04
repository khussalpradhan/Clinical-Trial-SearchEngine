# Search Engine Module (backend/search)

This module handles the **Hybrid Search** functionality of the Clinical Trial Search Engine, combining **Lexical Search (OpenSearch)** and **Semantic Search (FAISS)** to retrieve the most relevant clinical trials.

## Architecture

The search engine uses a two-pronged approach:

1.  **Lexical Search (OpenSearch)**:
    *   Handles exact keyword matching, filtering (Age, Gender, Phase, Status), and BM25 ranking.
    *   Stores the full trial metadata and structured criteria.
    *   **Source**: `reindex_from_postgres.py` syncs data from PostgreSQL to OpenSearch.

2.  **Semantic Search (FAISS)**:
    *   Handles conceptual matching (e.g., "heart attack" matches "myocardial infarction").
    *   Uses a pre-trained BERT model (`pritamdeka/S-PubMedBert-MS-MARCO`) to generate embeddings for trial descriptions and criteria.
    *   **Source**: `vector_search.py` performs dense retrieval using a pre-built FAISS index.

## Key Files

### 1. Indexing & ETL
- **`reindex_from_postgres.py`**: The main ETL script.
  - Connects to the local PostgreSQL database.
  - Fetches trials, sites, and criteria in chunks (server-side cursor).
  - Cleans and formats data (e.g., extracting "Inclusion Criteria" from raw text).
  - Bulk indexes documents into OpenSearch using the schema defined in `mapping.json`.

- **`mapping.json`**: Defines the OpenSearch index schema.
  - **Text Fields** (analyzed): `title`, `brief_summary`, `conditions`, `criteria_inclusion`, `criteria_exclusion`.
  - **Keyword Fields** (filtering): `nct_id`, `phase`, `overall_status`, `study_type`, `sex`.
  - **Nested Fields**: `locations` (facility, city, country).
  - **Stored Objects**: `parsed_criteria` (stored for retrieval but not indexed).

- **`init_index.py`**: Helper script to initialize the OpenSearch index with the mapping if it doesn't exist.

### 2. Vector Search
- **`vector_search.py`**: The runtime engine for semantic search.
  - **Lazy Loading**: Loads the FAISS index and BERT model only when the first search request is made (to speed up server start).
  - **Encoding**: Converts user queries into 768-dimensional vectors.
  - **Retrieval**: Returns the top-k `nct_ids` sorted by similarity score.

- **`build_faiss_index.py`**: (Offline) Script to generate the FAISS index.
  - Reads all trials.
  - Generates embeddings for them.
  - Saves the index to disk (`trials.index`) for `vector_search.py` to use.

## Usage

### Re-indexing Data
If you have updated the PostgreSQL database, run this command to sync changes to OpenSearch:

```bash
# Run from the project root
python -m backend.search.reindex_from_postgres
```

### Building Vector Index
To regenerate the semantic search index (e.g., after adding new trials):

```bash
python -m backend.search.build_faiss_index
```

## Search Logic (Hybrid)
The `backend.api.main` module combines results from these two systems:
1.  **Vector Search** retrieves the top ~50 semantically relevant trials.
2.  **OpenSearch** retrieves keyword-matched trials and applies hard filters (Age, Gender, Location).
3.  **RRF (Reciprocal Rank Fusion)** or **Linear Combination** merges the two lists to produce the final ranked result.
