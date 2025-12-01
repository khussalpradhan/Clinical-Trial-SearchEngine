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

# --- COMPREHENSIVE DISEASE LIST (100+ CONDITIONS) ---
# Covers all major disease categories in ClinicalTrials.gov
API_TARGETS = {
    # === CANCERS (Solid Tumors) ===
    "NSCLC": "C0007131",  # Non-Small Cell Lung Cancer
    "SCLC": "C0149925",  # Small Cell Lung Cancer
    "Breast_Cancer": "C0006142",
    "Prostate_Cancer": "C0033578",
    "Colorectal_Cancer": "C0009402",
    "Pancreatic_Cancer": "C0346647",
    "Ovarian_Cancer": "C0919267",
    "Cervical_Cancer": "C0007847",
    "Endometrial_Cancer": "C0007103",
    "Gastric_Cancer": "C0024623",  # Stomach Cancer
    "Esophageal_Cancer": "C0014859",
    "Bladder_Cancer": "C0005695",
    "Kidney_Cancer": "C0740457",  # Renal Cell Carcinoma
    "Liver_Cancer": "C0345904",  # Hepatocellular Carcinoma
    "Thyroid_Cancer": "C0007115",
    "Melanoma": "C0025202",  # Skin Cancer
    "Head_Neck_Cancer": "C0278996",
    "Glioblastoma": "C0017636",  # Brain Cancer
    "Mesothelioma": "C0025500",
    "Sarcoma": "C0036220",  # Soft Tissue/Bone
    "Neuroendocrine_Tumor": "C0206754",
    
    # === HEMATOLOGIC CANCERS ===
    "Leukemia": "C0023418",
    "AML": "C0023467",  # Acute Myeloid Leukemia
    "ALL": "C0023449",  # Acute Lymphoblastic Leukemia
    "CML": "C0023473",  # Chronic Myeloid Leukemia
    "CLL": "C0023434",  # Chronic Lymphocytic Leukemia
    "Multiple_Myeloma": "C0026764",
    "Lymphoma": "C0024299",
    "Hodgkin_Lymphoma": "C0019829",
    "Non_Hodgkin_Lymphoma": "C0024305",
    "Myelodysplastic_Syndrome": "C0026986",
    
    # === CARDIOVASCULAR ===
    "Heart_Failure": "C0018802",
    "Coronary_Artery_Disease": "C0010054",
    "Atrial_Fibrillation": "C0004238",
    "Hypertension": "C0020538",
    "Myocardial_Infarction": "C0027051",  # Heart Attack
    "Stroke": "C0038454",
    "Peripheral_Artery_Disease": "C0085096",
    "Cardiomyopathy": "C0878544",
    "Pulmonary_Hypertension": "C0020542",
    "Aortic_Stenosis": "C0003507",
    "Deep_Vein_Thrombosis": "C0149871",
    "Pulmonary_Embolism": "C0034065",
    
    # === METABOLIC/ENDOCRINE ===
    "Diabetes_Type_1": "C0011854",
    "Diabetes_Type_2": "C0011860",
    "Obesity": "C0028754",
    "Metabolic_Syndrome": "C0524620",
    "Hyperlipidemia": "C0020473",
    "Hypothyroidism": "C0020676",
    "Hyperthyroidism": "C0020550",
    "Osteoporosis": "C0029456",
    
    # === RESPIRATORY ===
    "COPD": "C0024117",  # Chronic Obstructive Pulmonary Disease
    "Asthma": "C0004096",
    "Pulmonary_Fibrosis": "C0034069",
    "Cystic_Fibrosis": "C0010674",
    "Sleep_Apnea": "C0037315",
    "Pneumonia": "C0032285",
    "Tuberculosis": "C0041296",
    "Respiratory_Failure": "C0035222",
    
    # === RENAL/UROLOGICAL ===
    "Chronic_Kidney_Disease": "C0022661",
    "Acute_Kidney_Injury": "C0022660",
    "End_Stage_Renal_Disease": "C0022661",
    "Nephrotic_Syndrome": "C0027726",
    "Benign_Prostatic_Hyperplasia": "C1704272",
    "Urinary_Tract_Infection": "C0042029",
    
    # === GASTROINTESTINAL ===
    "Crohns_Disease": "C0010346",
    "Ulcerative_Colitis": "C0009324",
    "Irritable_Bowel_Syndrome": "C0022104",
    "Cirrhosis": "C0023890",
    "Liver_Failure": "C0023895",
    "Hepatitis_B": "C0019163",
    "Hepatitis_C": "C0019196",
    "NASH": "C3241937",  # Non-Alcoholic Steatohepatitis
    "Gastroesophageal_Reflux": "C0017168",  # GERD
    "Celiac_Disease": "C0007570",
    
    # === NEUROLOGICAL ===
    "Alzheimers_Disease": "C0002395",
    "Parkinsons_Disease": "C0030567",
    "Multiple_Sclerosis": "C0026769",
    "Epilepsy": "C0014544",
    "Migraine": "C0149931",
    "ALS": "C0002736",  # Amyotrophic Lateral Sclerosis
    "Huntingtons_Disease": "C0020179",
    "Neuropathy": "C0442874",
    "Stroke": "C0038454",
    "Traumatic_Brain_Injury": "C0876926",
    
    # === PSYCHIATRIC ===
    "Major_Depression": "C0041696",
    "Bipolar_Disorder": "C0005586",
    "Schizophrenia": "C0036341",
    "Anxiety_Disorder": "C0003469",
    "PTSD": "C0038436",  # Post-Traumatic Stress Disorder
    "ADHD": "C1263846",  # Attention Deficit Hyperactivity Disorder
    "Autism_Spectrum_Disorder": "C1510586",
    "Obsessive_Compulsive_Disorder": "C0028768",
    
    # === RHEUMATOLOGIC/AUTOIMMUNE ===
    "Rheumatoid_Arthritis": "C0003873",
    "Osteoarthritis": "C0029408",
    "Systemic_Lupus_Erythematosus": "C0024141",  # SLE
    "Psoriasis": "C0033860",
    "Psoriatic_Arthritis": "C0003872",
    "Ankylosing_Spondylitis": "C0038013",
    "Sjogrens_Syndrome": "C0039082",
    "Scleroderma": "C0036421",
    "Vasculitis": "C0042384",
    "Gout": "C0018099",
    
    # === INFECTIOUS DISEASES ===
    "HIV": "C0019693",
    "COVID_19": "C5203670",
    "Influenza": "C0021400",
    "Sepsis": "C0243026",
    "Malaria": "C0024530",
    "HPV": "C0343641",  # Human Papillomavirus
    "CMV": "C0010823",  # Cytomegalovirus
    "Herpes_Simplex": "C0019348",
    
    # === DERMATOLOGIC ===
    "Eczema": "C0013595",
    "Acne": "C0001144",
    "Vitiligo": "C0042900",
    "Alopecia": "C0002170",
    
    # === HEMATOLOGIC (Non-Cancer) ===
    "Anemia": "C0002871",
    "Sickle_Cell_Disease": "C0002895",
    "Hemophilia": "C0019069",
    "Thrombocytopenia": "C0040034",
    "Von_Willebrand_Disease": "C0042974",
    
    # === OPHTHALMOLOGIC ===
    "Macular_Degeneration": "C0242383",
    "Glaucoma": "C0017601",
    "Diabetic_Retinopathy": "C0011884",
    "Cataracts": "C0856347",
    
    # === RARE DISEASES ===
    "Cystic_Fibrosis": "C0010674",
    "Duchenne_Muscular_Dystrophy": "C0013264",
    "Sickle_Cell_Disease": "C0002895",
    "Gaucher_Disease": "C0017205",
    "Fabry_Disease": "C0002986",
}

# --- COMPREHENSIVE BIOMARKER/LAB LIST (200+ TERMS) ---
# Covers all major biomarkers, genetic markers, and lab values used in clinical trials
MANUAL_BIOMARKERS = {
    # === CANCER GENETICS (Driver Mutations) ===
    "EGFR_Gene": [
        "EGFR", "Epidermal Growth Factor Receptor", "ERBB1", "HER1",
        "EGFR mutation", "EGFR positive",
        "Exon 19 deletion", "Ex19del", "Del19", "L858R", "T790M"
    ],
    "ALK_Gene": [
        "ALK", "Anaplastic Lymphoma Kinase", "ALK rearrangement", "ALK positive", "ALK fusion",
        "EML4-ALK"
    ],
    "ROS1_Gene": ["ROS1", "ROS1 rearrangement", "ROS1 positive", "ROS1 fusion"],
    "KRAS_Gene": [
        "KRAS", "K-Ras", "Ki-Ras", "KRAS mutation",
        "KRAS G12C", "KRAS G12D", "KRAS G12S", "KRAS G12V",
        "p.G12C", "c.34G>T"
    ],
    "NRAS_Gene": ["NRAS", "N-Ras", "NRAS mutation"],
    "BRAF_Gene": [
        "BRAF", "BRAF V600E", "BRAF mutation", "BRAF V600K",
        "p.V600E", "p.V600K", "c.1799T>A"
    ],
    "PIK3CA_Gene": ["PIK3CA", "PIK3CA mutation", "H1047R"],
    "MET_Gene": [
        "MET", "MET exon 14", "MET amplification", "c-MET",
        "MET exon 14 skipping", "METex14", "Exon 14 skipping"
    ],
    "RET_Gene": ["RET", "RET fusion", "RET rearrangement", "RET fusion positive"],
    "NTRK_Gene": [
        "NTRK", "NTRK fusion", "TRK fusion", "NTRK1", "NTRK2", "NTRK3",
        "ETV6-NTRK3"
    ],
    
    # === HEMATOLOGIC CANCER MARKERS ===
    "BCR_ABL_Gene": ["BCR-ABL", "Philadelphia Chromosome", "BCR/ABL", "BCR-ABL1"],
    "FLT3_Gene": ["FLT3", "FLT3-ITD", "FLT3 mutation", "FLT3-TKD"],
    "NPM1_Gene": ["NPM1", "NPM1 mutation"],
    "IDH1_Gene": ["IDH1", "IDH1 mutation", "IDH1 R132H"],
    "IDH2_Gene": ["IDH2", "IDH2 mutation"],
    "JAK2_Gene": ["JAK2", "JAK2 V617F", "JAK2 mutation"],
    "TP53_Gene": ["TP53", "p53", "TP53 mutation"],
    
    # === BREAST CANCER HORMONES & MARKERS ===
    "HER2_Receptor": ["HER2", "HER-2", "ERBB2", "HER-2/neu", "HER2 positive", "HER2 amplification"],
    "ER_Status": ["ER", "Estrogen Receptor", "ER positive", "ER+", "ESR1"],
    "PR_Status": ["PR", "Progesterone Receptor", "PR positive", "PR+", "PGR"],
    "BRCA1_Gene": ["BRCA1", "BRCA1 mutation"],
    "BRCA2_Gene": ["BRCA2", "BRCA2 mutation"],
    
    # === IMMUNOTHERAPY BIOMARKERS ===
    "PD_L1_Expression": ["PD-L1", "PDL1", "PD-L1 expression", "PD-L1 positive", "PD-L1 TPS"],
    "TMB": ["TMB", "Tumor Mutational Burden", "high TMB"],
    "MSI_Status": ["MSI", "MSI-H", "Microsatellite Instability", "dMMR", "mismatch repair deficient"],
    "CD19_Marker": ["CD19", "Cluster of Differentiation 19", "CD19 positive"],
    "CD20_Marker": ["CD20", "CD20 positive"],
    "CD38_Marker": ["CD38", "CD38 positive"],
    "BCMA_Marker": ["BCMA", "B-cell maturation antigen"],
    
    # === KIDNEY FUNCTION LABS ===
    "Creatinine_Level": ["Creatinine", "Serum Creatinine", "SCr", "sCr", "Cr"],
    "GFR_Level": ["GFR", "eGFR", "Glomerular Filtration Rate", "Creatinine Clearance", "CrCl"],
    "BUN_Level": ["BUN", "Blood Urea Nitrogen", "Urea"],
    "Albumin_Level": ["Albumin", "Serum Albumin"],
    "Protein_Urine": ["Proteinuria", "Urine Protein", "UACR"],
    
    # === LIVER FUNCTION LABS ===
    "Bilirubin_Level": ["Bilirubin", "Total Bilirubin", "Direct Bilirubin", "TBil", "TBIL"],
    "AST_Level": ["AST", "Aspartate Aminotransferase", "SGOT", "AST/SGOT"],
    "ALT_Level": ["ALT", "Alanine Aminotransferase", "SGPT", "ALT/SGPT"],
    "ALP_Level": ["ALP", "Alkaline Phosphatase"],
    "INR_Level": ["INR", "International Normalized Ratio", "Prothrombin Time", "PT"],
    "Albumin_Level": ["Albumin", "Serum Albumin"],
    
    # === CARDIAC LABS ===
    "BNP_Level": ["BNP", "NT-proBNP", "B-type Natriuretic Peptide", "Brain Natriuretic Peptide"],
    "LVEF_Score": ["LVEF", "Ejection Fraction", "Left Ventricular Ejection Fraction", "EF"],
    "Troponin_Level": ["Troponin", "Troponin I", "Troponin T", "cTnI", "cTnT"],
    "CK_MB_Level": ["CK-MB", "Creatine Kinase MB"],
    
    # === HEMATOLOGY (COMPLETE BLOOD COUNT) ===
    "Hemoglobin_Level": ["Hemoglobin", "Hgb", "Hb", "Hemoglobin level"],
    "Hematocrit_Level": ["Hematocrit", "HCT", "Hct"],
    "Platelet_Count": ["Platelets", "Platelet count", "PLT"],
    "WBC_Count": ["WBC", "White Blood Cell", "Leukocyte count"],
    "ANC_Level": ["ANC", "Absolute Neutrophil Count", "Neutrophils"],
    "Lymphocyte_Count": ["Lymphocytes", "Absolute Lymphocyte Count", "ALC"],
    "Monocyte_Count": ["Monocytes"],
    "Eosinophil_Count": ["Eosinophils"],
    
    # === COAGULATION ===
    "PTT_Level": ["PTT", "aPTT", "Activated Partial Thromboplastin Time"],
    "D_Dimer_Level": ["D-Dimer", "D-dimer"],
    "Fibrinogen_Level": ["Fibrinogen"],
    
    # === LIPID PANEL ===
    "Cholesterol_Total": ["Total Cholesterol", "Cholesterol"],
    "LDL_Cholesterol": ["LDL", "LDL Cholesterol", "Low-Density Lipoprotein"],
    "HDL_Cholesterol": ["HDL", "HDL Cholesterol", "High-Density Lipoprotein"],
    "Triglycerides_Level": ["Triglycerides", "TG"],
    
    # === DIABETES/METABOLIC ===
    "HbA1c_Level": ["HbA1c", "Hemoglobin A1c", "Glycated Hemoglobin", "A1C"],
    "Glucose_Level": ["Glucose", "Blood Glucose", "Fasting Glucose", "FBG"],
    "Insulin_Level": ["Insulin", "Fasting Insulin"],
    
    # === THYROID FUNCTION ===
    "TSH_Level": ["TSH", "Thyroid Stimulating Hormone", "Thyrotropin"],
    "T4_Level": ["T4", "Thyroxine", "Free T4", "FT4"],
    "T3_Level": ["T3", "Triiodothyronine", "Free T3", "FT3"],
    
    # === TUMOR MARKERS ===
    "PSA_Level": ["PSA", "Prostate Specific Antigen"],
    "CEA_Level": ["CEA", "Carcinoembryonic Antigen"],
    "CA_125_Level": ["CA-125", "CA 125", "Cancer Antigen 125"],
    "CA_19_9_Level": ["CA 19-9", "CA19-9", "Cancer Antigen 19-9"],
    "AFP_Level": ["AFP", "Alpha-Fetoprotein"],
    "Beta_hCG_Level": ["Beta-hCG", "hCG", "Human Chorionic Gonadotropin"],
    
    # === INFLAMMATION MARKERS ===
    "CRP_Level": ["CRP", "C-Reactive Protein", "hs-CRP"],
    "ESR_Level": ["ESR", "Erythrocyte Sedimentation Rate", "Sed Rate"],
    
    # === ELECTROLYTES ===
    "Sodium_Level": ["Sodium", "Na", "Serum Sodium"],
    "Potassium_Level": ["Potassium", "K", "Serum Potassium"],
    "Calcium_Level": ["Calcium", "Ca", "Serum Calcium"],
    "Magnesium_Level": ["Magnesium", "Mg"],
    "Phosphate_Level": ["Phosphate", "Phosphorus"],
    "Chloride_Level": ["Chloride", "Cl"],
    
    # === HORMONES ===
    "Testosterone_Level": ["Testosterone", "Serum Testosterone", "Total Testosterone"],
    "Estradiol_Level": ["Estradiol", "E2"],
    "Cortisol_Level": ["Cortisol"],
    "Vitamin_D_Level": ["Vitamin D", "25-OH Vitamin D", "25-hydroxyvitamin D"],
    
    # === BONE MARKERS ===
    "Bone_Alkaline_Phosphatase": ["Bone-specific ALP", "BSAP"],
    "CTX_Level": ["CTX", "C-telopeptide"],
    "Osteocalcin_Level": ["Osteocalcin"],
    
    # === VIRAL LOADS ===
    "HIV_Viral_Load": ["HIV RNA", "HIV viral load", "HIV-1 RNA"],
    "HBV_DNA_Level": ["HBV DNA", "Hepatitis B viral load"],
    "HCV_RNA_Level": ["HCV RNA", "Hepatitis C viral load"],
    
    # === AUTOIMMUNE MARKERS ===
    "ANA_Level": ["ANA", "Antinuclear Antibody"],
    "RF_Level": ["RF", "Rheumatoid Factor"],
    "Anti_CCP_Level": ["Anti-CCP", "Anti-Cyclic Citrullinated Peptide"],
    
    # === OTHER IMPORTANT MARKERS ===
    "Lactate_Level": ["Lactate", "Lactic Acid"],
    "Ammonia_Level": ["Ammonia", "NH3"],
    "Uric_Acid_Level": ["Uric Acid"],
    "Ferritin_Level": ["Ferritin", "Serum Ferritin"],
    "Iron_Level": ["Iron", "Serum Iron"],
    "TIBC_Level": ["TIBC", "Total Iron Binding Capacity"],
    "B12_Level": ["Vitamin B12", "Cobalamin"],
    "Folate_Level": ["Folate", "Folic Acid"],
}

# Manual disease synonyms to augment UMLS results (high-impact subtypes/aliases)
MANUAL_DISEASE_SYNONYMS = {
    "Breast_Cancer": [
        "Triple negative breast cancer", "TNBC",
        "HER2-positive breast cancer", "HER2+ breast cancer",
        "ER-positive breast cancer", "ER+/PR+ breast cancer",
        "Luminal A", "Luminal B"
    ],
    "NSCLC": [
        "EGFR-mutant NSCLC", "ALK-positive NSCLC", "ROS1-positive NSCLC",
        "KRAS G12C NSCLC", "PD-L1 high NSCLC"
    ],
    "Liver_Cancer": ["Hepatocellular carcinoma", "HCC"],
    "Kidney_Cancer": ["Renal cell carcinoma", "RCC", "Clear cell RCC"],
    "Glioblastoma": ["GBM", "Glioblastoma multiforme"],
    "Head_Neck_Cancer": [
        "Head and neck squamous cell carcinoma", "HNSCC"
    ],
    "Colorectal_Cancer": ["CRC", "Colorectal carcinoma"],
    "Ovarian_Cancer": ["High-grade serous ovarian cancer", "HGSOC"],
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
        # Merge with manual disease synonyms (if any)
        manual = MANUAL_DISEASE_SYNONYMS.get(name, [])
        merged = list({*(syns or []), *manual})
        output_data[name] = merged
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