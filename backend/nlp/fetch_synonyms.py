import requests
import json
import time
import os

# --- CONFIGURATION ---
API_KEY = os.environ.get("UMLS_API_KEY")

# Fallback for local testing (Do not commit real keys!)
if not API_KEY:
    pass

if not API_KEY:
    raise RuntimeError(
        "Environment variable UMLS_API_KEY is not set.\n"
        "Set it locally (e.g. `export UMLS_API_KEY=\"...\"`) before running this script."
    )

BASE_URI = "https://uts-ws.nlm.nih.gov/rest"

# --- EXPANDED DISEASE LIST ---
API_TARGETS = {
    # Original Scope
    "NSCLC": "C0007131",          
    "Breast_Cancer": "C0006142",  
    "Heart_Failure": "C0018802",
    "Chronic_Kidney_Disease": "C0022661",
    
    # New Additions (Organ Failure)
    "Respiratory_Failure": "C0035222", # Lung Failure
    "Liver_Failure": "C0023895",
    
    # New Additions (Cancers)
    "Leukemia": "C0023418",            # Blood Cancer
    "Prostate_Cancer": "C0033578",
    "Skin_Cancer": "C0037286",         # Melanoma & Non-melanoma
    "Cervical_Cancer": "C0007847",
    "Bone_Cancer": "C0005967"
}

# --- EXPANDED BIOMARKER/LAB LIST ---
MANUAL_BIOMARKERS = {
    # Cancer Genetics
    "EGFR_Gene": ["EGFR", "Epidermal Growth Factor Receptor", "ERBB1", "HER1", "EGFR mutation"],
    "HER2_Receptor": ["HER2", "HER-2", "ERBB2", "HER-2/neu", "HER2 positive"],
    "ALK_Gene": ["ALK", "Anaplastic Lymphoma Kinase", "ALK rearrangement", "ALK positive"],
    "KRAS_Gene": ["KRAS", "K-Ras", "Ki-Ras", "KRAS mutation", "KRAS G12C"],

    # Kidney Labs
    "Creatinine_Level": ["Creatinine", "Serum Creatinine", "SCr", "sCr"],
    "GFR_Level": ["GFR", "eGFR", "Glomerular Filtration Rate", "Creatinine Clearance", "CrCl"],

    # Liver Labs (NEW)
    "Bilirubin_Level": ["Bilirubin", "Total Bilirubin", "Direct Bilirubin", "TBil"],
    "AST_Level": ["AST", "Aspartate Aminotransferase", "SGOT"],
    "ALT_Level": ["ALT", "Alanine Aminotransferase", "SGPT"],
    
    # Prostate Labs (NEW)
    "PSA_Level": ["PSA", "Prostate Specific Antigen"]
}

def get_synonyms(cui, api_key):
    uri = f"{BASE_URI}/content/current/CUI/{cui}/atoms"
    params = {
        "apiKey": api_key, 
        "sabs": "SNOMEDCT_US,NCI,RXNORM", 
        "language": "ENG",
        "pageSize": 50
    }
    
    try:
        response = requests.get(uri, params=params)
        response.raise_for_status()
        data = response.json()
        
        synonyms = set()
        for result in data.get("result", []):
            synonyms.add(result["name"])
            
        return list(synonyms)
    except Exception as e:
        print(f"Error fetching {cui}: {e}")
        return []

if __name__ == "__main__":
    print("Starting Expanded Ingestion...")
    output_data = {}

    # 1. Fetch Diseases
    for name, cui in API_TARGETS.items():
        print(f"   Searching API for: {name}...")
        syns = get_synonyms(cui, API_KEY)
        output_data[name] = syns
        print(f"   Found {len(syns)} terms.")
        time.sleep(0.2) 

    # 2. Inject Biomarkers
    print("   Injecting manual biomarker lists...")
    output_data.update(MANUAL_BIOMARKERS)

    # 3. Save
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "clinical_synonyms.json")
    
    with open(file_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nSuccess! Dictionary saved to: {file_path}")