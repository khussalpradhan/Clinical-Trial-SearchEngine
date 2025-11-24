import requests
import json
import time
import os

# --- CONFIGURATION ---
API_KEY = "d75d89f7-7280-4e9f-be97-ecebb9773374"  # <--- PASTE YOUR KEY HERE
BASE_URI = "https://uts-ws.nlm.nih.gov/rest"

# Only fetch these from API (Conditions have many variations)
API_TARGETS = {
    "NSCLC": "C0007131",          
    "Breast_Cancer": "C0006142",  
    "Heart_Failure": "C0018802"
}

# Hardcode these (Biomarkers are standard acronyms
MANUAL_BIOMARKERS = {
    "EGFR_Gene": [
        "EGFR", "Epidermal Growth Factor Receptor", "ERBB1", "HER1", 
        "EGFR mutation", "EGFR positive"
    ],
    "HER2_Receptor": [
        "HER2", "HER-2", "ERBB2", "HER-2/neu", 
        "Human Epidermal Growth Factor Receptor 2", "HER2 positive"
    ],
    "ALK_Gene": [
        "ALK", "Anaplastic Lymphoma Kinase", "ALK rearrangement", 
        "ALK positive", "ALK fusion"
    ],
    "KRAS_Gene": [
        "KRAS", "K-Ras", "Ki-Ras", "KRAS mutation", 
        "KRAS G12C", "Kirsten rat sarcoma viral oncogene homolog"
    ]
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
    print("Starting Hybrid Ingestion...")
    output_data = {}

    # 1. Fetch Diseases from API
    for name, cui in API_TARGETS.items():
        print(f"Searching API for: {name}...")
        syns = get_synonyms(cui, API_KEY)
        output_data[name] = syns
        print(f"   Found {len(syns)} terms.")
        time.sleep(0.2) 

    # 2. Inject Manual Biomarkers
    print("Injecting manual biomarker lists...")
    output_data.update(MANUAL_BIOMARKERS)

    # 3. Save
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "clinical_synonyms.json")
    
    with open(file_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Dictionary saved to: {file_path}")
