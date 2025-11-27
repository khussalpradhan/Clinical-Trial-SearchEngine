# NLP setup (backend/nlp)

This folder contains helper scripts for building the clinical synonyms dictionary and testing the `CriteriaParser` against real trial data.

Overview

- `fetch_synonyms.py` — hybrid ingestion: fetches synonym lists for configured UMLS CUIs and writes `clinical_synonyms.json` into this folder. It also injects a set of manual biomarker synonyms.
- `test_real_data.py` — connects to a Postgres database (defaults are configured inside the script) and runs the `CriteriaParser` on a small random sample of trials.

Prerequisites

- Python 3.8+ (use a virtual environment)
- Postgres database with the schema from `backend/db/schema.sql` loaded and data available if you want to run `test_real_data.py`.
- A UMLS API key (if you want to fetch synonyms from the UMLS API).

Environment variables

- `UMLS_API_KEY` — your UMLS (NLM) API key. Do NOT hardcode keys in source control.
  - Set it for the session (macOS / zsh):

    ```bash
    export UMLS_API_KEY="your-real-key-here"
    ```

  - Persist it in `~/.zshrc` if desired:

    ```bash
    echo 'export UMLS_API_KEY="your-real-key-here"' >> ~/.zshrc
    source ~/.zshrc
    ```

Notes:
- `requirements.txt` already includes `requests`, `psycopg2-binary`, and `python-dotenv`.
- Optional: install `spaCy` and the small English model for better parsing:

```bash
pip install spacy
python -m spacy download en_core_web_sm
```

Running `fetch_synonyms.py`

1. Ensure `UMLS_API_KEY` is exported in your shell.
2. From `backend` (or pass a full path), run:

```bash
python3 nlp/fetch_synonyms.py
```

What this does:
- Calls the UMLS REST endpoint for configured CUIs in `fetch_synonyms.py` and collects returned atom names.
- Merges with `MANUAL_BIOMARKERS` and writes `clinical_synonyms.json` in `backend/nlp/`.

Running `test_real_data.py`

`test_real_data.py` connects to Postgres using the `DB_CONFIG` defined at the top of the file. Default values are:

```python
DB_CONFIG = {
    "dbname": "clinical_trials",
    "user": "clinical_user",
    "password": "clinical_pass",
    "host": "localhost",
    "port": "5432"
}
```

To run the test:

```bash
python3 nlp/test_real_data.py
```

What to expect:
- The script will connect to Postgres, count rows in `trials`, and select 5 random trials that have `eligibility_criteria_raw`.
- It prints `nct_id`, `brief_title`, and the extracted `conditions` / `biomarkers` (if any).

Schema notes

- `test_real_data.py` was updated to use columns present in `backend/db/schema.sql`: `brief_title` and `eligibility_criteria_raw` (instead of the earlier `title`/`criteria`). If you customized your schema, update the query in `test_real_data.py`.

Troubleshooting

- `Environment variable UMLS_API_KEY is not set.` — export the key then re-run.
- `psycopg2` connection errors — ensure Postgres is running and `DB_CONFIG` is correct.
- SQL errors about missing columns — confirm your DB schema matches `backend/db/schema.sql`.
- If `spacy` import fails, install `spacy` and the English model or allow the parser to run in fallback mode (it will not crash but will be less feature-rich).

Recent Changes (Nov 26, 2025)

- `fetch_synonyms.py`
  - Replaced hardcoded API key with an environment variable `UMLS_API_KEY`.
  - Added comments and a clear runtime error if the key is not set to prevent committing secrets.

- `criteria_parser.py`
  - Restored a clean `CriteriaParser` implementation after the file was corrupted.
  - Improved regexes and word-boundary matching, added additional biomarker keys (`Creatinine_Level`, `GFR_Level`).
  - Added a runnable demo block; execute `python3 backend/nlp/criteria_parser.py` to run a quick example.

- `test_real_data.py`
  - Fixed SQL to use `brief_title` and `eligibility_criteria_raw` (matches `backend/db/schema.sql`).
  - Updated prints/variables to display `brief_title` and parsed results for each trial.

Quick recap of useful commands

```bash
# Export UMLS key for the session (macOS / zsh)
export UMLS_API_KEY="your-real-key-here"

# Run fetch_synonyms (creates backend/nlp/clinical_synonyms.json)
cd backend
source .venv/bin/activate
python3 nlp/fetch_synonyms.py

# Run parser demo
python3 backend/nlp/criteria_parser.py

# Run DB-backed test
python3 backend/nlp/test_real_data.py
```