import psycopg2
import sys
import os

try:
    from feasibility_scorer import FeasibilityScorer
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from feasibility_scorer import FeasibilityScorer

# --- DOCKER CONFIGURATION ---
DB_CONFIG = {
    "dbname": "clinical_trials",
    "user": "clinical_user",
    "password": "clinical_pass",
    "host": "localhost",
    "port": "5432"
}

# --- DEFINE A FAKE PATIENT ---
# Let's pretend we are looking for a Lung Cancer patient
FAKE_PATIENT = {
    "age": 65,
    "gender": "Female",
    "ecog": 1,
    "conditions": ["NSCLC"],
    "biomarkers": ["EGFR"],
    "labs": {
        "Creatinine": 1.2,
        "Bilirubin": 0.8,
        "AST": 30
    }
}

def test_scoring_engine():
    print(" Initializing Feasibility Scorer...", flush=True)
    scorer = FeasibilityScorer()

    print(f" Connecting to Database...", flush=True)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
    except Exception as e:
        print(f" Connection Failed: {e}")
        return

    # Fetch 20 NSCLC trials to test against our fake patient
    query = """
    SELECT nct_id, brief_title, eligibility_criteria_raw
    FROM trials
    WHERE eligibility_criteria_raw IS NOT NULL
    AND eligibility_criteria_raw ILIKE '%non-small cell%'
    LIMIT 20;
    """
    
    cur.execute(query)
    rows = cur.fetchall()
    
    print(f"\n Scoring Patient: 65yo Female, NSCLC, EGFR+, ECOG 1", flush=True)
    print("=" * 60)

    for row in rows:
        nct_id, title, criteria = row
        
        # --- THE MAGIC HAPPENS HERE ---
        result = scorer.score_patient(FAKE_PATIENT, criteria)
        
        # Only show interesting results (Feasible or High Score)
        if result['score'] > 0 or result['is_feasible']:
            print(f"\n Trial: {nct_id}")
            print(f"   Score: {result['score']}/100 {' FEASIBLE' if result['is_feasible'] else ' INFEASIBLE'}")
            print(f"   Reasons: {result['reasons']}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    test_scoring_engine()