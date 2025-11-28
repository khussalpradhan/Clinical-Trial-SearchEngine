# NLP Feasibility Engine (backend/nlp)

This module contains the NLP and scoring logic used by the Clinical Trial Search Engine. It parses unstructured eligibility criteria, extracts clinical entities, and computes a feasibility score (0–100) for a given patient profile.

## Key Files

- `criteria_parser.py` — NLP extraction engine (regex + optional spaCy). Extracts: conditions, biomarkers, lab thresholds, demographics (age/gender), hard exclusions, temporal rules, and treatment-history constraints.
- `feasibility_scorer.py` — Scoring logic that compares a `patient_profile` with parsed trial data and returns a score and reasons.
- `fetch_synonyms.py` — Hybrid ingestion script that fetches synonyms from UMLS for configured CUIs and merges with manually curated biomarker/lab synonyms. Generates `clinical_synonyms.json`.
- `clinical_synonyms.json` — Generated dictionary used by the parser for matching.
- `test_real_data.py` — Integration runner that pulls trials from local Postgres and runs the parser.
- `test_scorer.py` — Runner that creates fake patient profiles and scores them against real trials.

---

## API Documentation

### Main function (example)

Import guideline (when used from the backend package):

```python
from backend.nlp import rank_trials  # if exposed by package __init__
```

### Example: `patient_profile` (python)

```python
patient_profile = {
    # Demographics
    "age": 65,
    "gender": "Female",

    # Clinical Status
    "ecog": 1,
    "conditions": ["NSCLC"],

    # Genetics / Biomarkers
    "biomarkers": ["EGFR", "HER2"],

    # Lab Values
    "labs": {
        "Creatinine": 1.2,
        "GFR": 45,
        "Bilirubin": 0.8,
        "AST": 35,
        "ALT": 40,
        "Platelet_Count": 150,
        "Hemoglobin": 11.0,
        "PSA": 2.5
    },

    # Treatment History
    "prior_lines": 1,
    "days_since_last_treatment": 30
}
```

---

## Prerequisites

1. Python 3.8+ (use a virtualenv for isolation).
2. Postgres database populated with the schema in `backend/db/schema.sql` (if you plan to run `test_real_data.py` / `test_scorer.py`).
3. UMLS API key (only required if you will run `fetch_synonyms.py`).

### Environment variables

Export your UMLS API key (macOS / zsh example):

```bash
export UMLS_API_KEY="your-real-key-here"
```

(You can add that line to `~/.zshrc` to persist across sessions.)

---

## Setup & Install

From the `backend` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional: install spaCy and the small English model for richer parsing:

```bash
pip install spacy
python -m spacy download en_core_web_sm
```

---

## Running the scripts

- Fetch synonyms (writes `backend/nlp/clinical_synonyms.json`):

```bash
# ensure UMLS_API_KEY is set in your environment
python3 nlp/fetch_synonyms.py
```

- Parser demo (runs a small example):

```bash
python3 backend/nlp/criteria_parser.py
```

- Run the scorer test (ensure DB credentials in `test_scorer.py` or environment are correct):

```bash
python3 backend/nlp/test_scorer.py
```

- Run the real-data integration parser:

```bash
python3 backend/nlp/test_real_data.py
```

---

## Recent Changes (Nov 26–27, 2025)

- `fetch_synonyms.py`: removed hardcoded UMLS key and now reads `UMLS_API_KEY` from the environment; added clear error message when missing.
- `criteria_parser.py`: restored clean implementation; improved regexes and word-boundary matching; added demo `__main__` block for quick checks.
- `feasibility_scorer.py`: made imports robust for script vs package usage; (previously broken by relative imports when executed directly).
- `test_real_data.py` / `test_scorer.py`: updated SQL to use `brief_title` and `eligibility_criteria_raw` matching `backend/db/schema.sql`.
- `backend/nlp/README.md`: rewritten and cleaned to remove erroneous code fences and provide clear run instructions.

---

## Troubleshooting

- If `fetch_synonyms.py` errors with `Environment variable UMLS_API_KEY is not set.`, export the key then re-run.
- If `psycopg2` connection errors appear, verify Postgres is running and DB credentials are correct.
- If parsing returns empty conditions/biomarkers, make sure `backend/nlp/clinical_synonyms.json` exists (run `fetch_synonyms.py`) and contains the expected keys.

---

If you'd like, I can:

- Add `.env` auto-loading to `fetch_synonyms.py` (via `python-dotenv`) so you can use a local `.env` file.
- Make `test_scorer.py` read DB credentials from environment variables rather than hard-coded `DB_CONFIG`.
- Add unit tests for `CriteriaParser` and `FeasibilityScorer`.

Tell me which of these you'd like next.
