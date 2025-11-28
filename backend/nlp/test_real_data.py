print("DEBUG: Script is starting...", flush=True)

import psycopg2
import sys
import os

# --- IMPORT CONFIGURATION ---
try:
    from criteria_parser import CriteriaParser 
except ImportError:
    # Fallback if running from root directory
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from criteria_parser import CriteriaParser

# --- DATABASE CONFIGURATION ---
DB_CONFIG = {
    "dbname": "clinical_trials",
    "user": "clinical_user",
    "password": "clinical_pass",
    "host": "localhost",
    "port": "5432"
}

def test_on_real_data():
    print("Loading Parser...", flush=True)
    parser = CriteriaParser()

    print(f"Connecting to Docker DB at {DB_CONFIG['host']}...", flush=True)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("Success: Connected to Database.", flush=True)
    except Exception as e:
        print(f"\nCONNECTION FAILED: {e}")
        return

    # Check row count
    try:
        cur.execute("SELECT COUNT(*) FROM trials;")
        count = cur.fetchone()[0]
        print(f"Total rows in database: {count}", flush=True)
        
        if count == 0:
            print("\nERROR: Database is empty. Please run the ingestion script first.")
            return
    except Exception as e:
        print(f"Failed to count rows: {e}")
        return

    # --- UPDATED QUERY: SEARCH FOR ALL 11 CONDITIONS ---
    print("Fetching trials for ALL supported diseases...", flush=True)
    
    query = """
    SELECT nct_id, brief_title, eligibility_criteria_raw
    FROM trials
    WHERE eligibility_criteria_raw IS NOT NULL
    AND (
        -- Original Scope
        eligibility_criteria_raw ILIKE '%non-small cell%' OR 
        eligibility_criteria_raw ILIKE '%breast cancer%' OR
        eligibility_criteria_raw ILIKE '%heart failure%' OR
        
        -- Kidney
        eligibility_criteria_raw ILIKE '%chronic kidney%' OR
        eligibility_criteria_raw ILIKE '%renal failure%' OR
        
        -- Organ Failures
        eligibility_criteria_raw ILIKE '%liver failure%' OR
        eligibility_criteria_raw ILIKE '%respiratory failure%' OR
        
        -- New Cancers
        eligibility_criteria_raw ILIKE '%leukemia%' OR 
        eligibility_criteria_raw ILIKE '%prostate cancer%' OR
        eligibility_criteria_raw ILIKE '%skin cancer%' OR
        eligibility_criteria_raw ILIKE '%melanoma%' OR
        eligibility_criteria_raw ILIKE '%cervical cancer%' OR
        eligibility_criteria_raw ILIKE '%bone cancer%' OR
        eligibility_criteria_raw ILIKE '%osteosarcoma%'
    )
    ORDER BY RANDOM()
    LIMIT 100; 
    """
    # Increased LIMIT to 10 to give you a better chance of seeing variety
    
    try:
        cur.execute(query)
        rows = cur.fetchall()
    except Exception as e:
        print(f"Query Failed: {e}")
        print("Suggestion: Check schema.sql for correct column names.")
        return

    print(f"\nTesting on {len(rows)} targeted trials...", flush=True)
    print("-" * 60)
    
    for row in rows:
        nct_id, brief_title, raw_text = row
        print(f"\nTrial ID: {nct_id}")
        print(f"Title:    {brief_title[:80]}...") 
        
        structured_data = parser.parse(raw_text)
        
        # --- PRINT PARSED DATA ---
        has_data = False

        if structured_data.get('conditions'):
            print(f"   Conditions: {structured_data['conditions']}")
            has_data = True
        
        if structured_data.get('ecog'):
            print(f"   ECOG:       {structured_data['ecog']}")
            has_data = True
        
        if structured_data.get('labs'):
            print(f"   Labs:       {structured_data['labs']}")
            has_data = True
            
        if structured_data.get('biomarkers'):
            print(f"   Biomarkers: {structured_data['biomarkers']}")
            has_data = True

        age = structured_data.get('age_range')
        if age and age != [0, 100]:
            print(f"   Age Range:  {age}")
            has_data = True

        gender = structured_data.get('gender')
        if gender and gender != "All":
            print(f"   Gender:     {gender}")
            has_data = True
            
        if not has_data:
            print("   (No specific entities extracted; defaults applied)")

    cur.close()
    conn.close()

if __name__ == "__main__":
    test_on_real_data()