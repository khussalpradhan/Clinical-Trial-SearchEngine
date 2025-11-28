# NLP Feasibility Engine (backend/nlp)

This module houses the core intelligence of the Clinical Trial Search Engine. It is responsible for parsing unstructured eligibility criteria, extracting clinical entities, and calculating a match score (0-100) for a specific patient.

## Key Files

### 1. Core Logic
- **`criteria_parser.py`**: The NLP engine. Uses regex and spaCy to extract specific clinical data:
  - **Conditions:** (NSCLC, Breast Cancer, Heart Failure, Chronic Kidney Disease, Respiratory Failure, Liver Failure, Leukemia, Prostate Cancer, Skin Cancer, Cervical Cancer, Bone Cancer)
  - **Biomarkers/Genetics:** (EGFR, HER2, ALK, KRAS, BRAF, BCR-ABL, FLT3, CD19, ER_Status, PR_Status)
  - **Lab Values:** (Creatinine, GFR, Bilirubin, AST, ALT, INR, PSA, Testosterone, BNP, LVEF, Platelets, Hemoglobin, ANC)
  - **Demographics:** (Age Range [Min/Max], Gender [Male/Female/All])
  - **Hard Exclusions:** (CNS Metastases, HIV, Hepatitis B/C, Pregnancy/Lactation, Prior Malignancy)
  - **Temporal Rules:** (Washout periods for chemotherapy or surgery in days/weeks)
  - **Treatment History:** (Min/Max allowed Lines of Therapy, Treatment Naïve status)

- **`feasibility_scorer.py`**: The judgment engine. Compares a Patient Profile against the parsed trial data to calculate a score based on weighted logic:
  - **Hard Exclusions:** (Score = 0 if patient has a banned condition like Pregnancy or CNS Mets)
  - **Condition Match:** (+40 points if the trial explicitly treats the patient's disease)
  - **Biomarker Match:** (+25 points if patient matches a required genomic marker like EGFR or HER2)
  - **ECOG Status:** (+15 points if patient's ECOG score is within the trial's allowed range)
  - **Lines of Therapy:** (+10 points if patient's prior history fits the trial's specific window, e.g. 2nd Line)
  - **Lab Thresholds:** (+10 points per passed lab value, e.g. Creatinine < 1.5)
  - **Age:** (+5 points for demographic fit)
  - **Gender:** (+5 points for demographic fit)
  - **Washout Periods:** (+5 points if patient clears required washout days)

- **`__init__.py`**: The API entry point. Exposes the `rank_trials(patient, trials)` function for the backend to use.

### 2. Data & Setup
- **`fetch_synonyms.py`**: A hybrid ingestion script. It fetches synonyms from the UMLS API for the 11 targeted conditions and injects the manually curated list of biomarkers/labs. Generates `clinical_synonyms.json`.
- **`clinical_synonyms.json`**: The "Gold Standard" dictionary used by the parser for entity recognition.

### 3. Testing
- **`test_real_data.py`**: Integration test. Connects to the local Dockerized Postgres DB, pulls real trials via SQL `ILIKE` queries, and verifies that the parser correctly extracts entities from raw text.
- **`test_scorer.py`**: Unit test for the scoring logic. Creates "Fake Patients" (e.g., Stage IV NSCLC, ECOG 1, Creatinine 1.2) and scores them against real trials to verify ranking accuracy.

##  API Documentation

### Main Function: `rank_trials(patient_profile, trials_list)`

Imports: `from backend.nlp import rank_trials`

#### 1. Input: `patient_profile` (Dictionary)
This dictionary represents the patient's clinical state. All fields are optional but recommended for better scoring.

```python
patient_profile = {
    # Demographics
    "age": 65,                  # int: Age in years
    "gender": "Female",         # str: "Male" or "Female"
    
    # Clinical Status
    "ecog": 1,                  # int: ECOG Performance Status (0-5)
    "conditions": ["NSCLC"],    # list[str]: Diagnosed conditions (must match dictionary keys)
    
    # Genetics / Biomarkers
    "biomarkers": ["EGFR", "HER2"], # list[str]: Positive biomarkers
    
    # Lab Values (Dictionary of value per lab)
    "labs": {
        "Creatinine": 1.2,      # float: mg/dL
        "GFR": 45,              # float: mL/min
        "Bilirubin": 0.8,
        "AST": 35,
        "ALT": 40,
        "Platelet_Count": 150,
        "Hemoglobin": 11.0,
        "PSA": 2.5
    },
    
    # Treatment History
    "prior_lines": 1,           # int: Number of prior systemic therapy lines
    "days_since_last_treatment": 30 # int: Days since last chemo/surgery (for washout checks)
}
```
---
## 🛠 Prerequisites

1. **Python 3.8+** (Recommended to use the project's virtual environment).
2. **Postgres Database**: You must have the Docker container running and populated with data (`backend/db/scrape_clinical_trials.py` must have been run).
3. **UMLS API Key**: Required to regenerate the dictionary.

### Environment Variables
You need a UMLS (NLM) API key to run `fetch_synonyms.py`.
```bash
export UMLS_API_KEY="your-real-key-here"