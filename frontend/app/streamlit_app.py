import sys
from pathlib import Path
import streamlit as st

# Ensure imports work
frontend_root = Path(__file__).parent.parent.resolve()
if str(frontend_root) not in sys.path:
    sys.path.append(str(frontend_root))

from api_clients.trial_api import rank_trials  # Import from api_clients
from app.ui.results_panel import render_results

# ============================================
# Streamlit Page Config
# ============================================
st.set_page_config(
    page_title="Clinical Trial Finder",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# Global Dark Theme CSS
# ============================================
st.markdown("""
<style>
 @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');

html, body, div, p { font-family: 'Inter', sans-serif !important; }

body, .stApp {
    background-color: #000 !important;
    color: white !important;
}

.block-container { padding-top: 2rem; max-width: 1150px; }
.section-title { font-size:1.5rem; font-weight:700; color:white; margin-bottom:10px; margin-top:20px; }
.trial-card { margin-bottom:15px; padding:20px; border-radius:12px; border:1px solid #222; background:#111; }
.trial-card h3, .trial-card p { color:white; }
</style>
""", unsafe_allow_html=True)



# ============================================
# Session State Navigation
# ============================================


if "page" not in st.session_state:
    st.session_state.page = "main"

if "selected_trial" not in st.session_state:
    st.session_state.selected_trial = None


# ============================================
# TRIAL DETAILS PAGE
# ============================================
# ============================================
# Session State Navigation
# ============================================

if "page" not in st.session_state:
    st.session_state.page = "main"

if "selected_trial" not in st.session_state:
    st.session_state.selected_trial = None


# ============================================
# TRIAL DETAILS PAGE
# ============================================
if st.session_state.page == "trial":
    
    # Scroll to top on load
    st.markdown("""
    <script>
    window.onload = function() {
        window.parent.document.querySelector('.main').scrollTo(0, 0);
        window.scrollTo(0, 0);
    };
    </script>
    """, unsafe_allow_html=True)

    trial = st.session_state.selected_trial

    if not trial:
        st.error("No trial selected.")
        st.button("Back to Search", on_click=lambda: st.session_state.update(page="main"))
        st.stop()

    # ============================================
    # Trial Page CSS
    # ============================================
    st.markdown("""
    <style>
        .trial-container {
            background-color:#111;
            border:1px solid #222;
            padding:35px;
            border-radius:16px;
            margin-top:10px;
        }

        .trial-title {
            font-size:2.6rem;
            font-weight:800;
            color:white;
            margin-bottom:15px;
            line-height:1.2;
        }

        .trial-official-title {
            font-size:2.3rem;
            font-weight:800;
            color:white;
            margin-bottom:25px;
            line-height:1.3;
        }

        .detail-grid {
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:28px 50px;
            margin-bottom:25px;
        }

        .detail-label {
            font-size:1rem;
            color:#aaa;
            font-weight:700;
            text-transform:uppercase;
            margin-bottom:12px;
            margin-top:20px;
        }

        .detail-value {
            font-size:1.15rem;
            color:#fff;
            font-weight:500;
            word-wrap: break-word;
        }

        .summary-title {
            font-size:1rem;
            font-weight:700;
            color:#aaa;
            text-transform:uppercase;
            margin-top:20px;
            margin-bottom:12px;
        }

        .summary-text {
            font-size:1.15rem;
            color:#fff;
            font-weight:500;
            word-wrap: break-word;
        }

        /* Styling for Centered, Small Back Button */
        .back-button {
            padding: 8px 15px;
            background-color: #007BFF;
            color: white;
            border-radius: 8px;
            cursor: pointer;
            text-align: center;
            font-size: 0.9rem;
            margin-top: 30px;
            display: block;
            width: 200px;
            margin-left: auto;
            margin-right: auto;
        }

        .back-button:hover {
            background-color: #0056b3;
        }
    </style>
    """, unsafe_allow_html=True)

    # ============================================
    # TITLE & OFFICIAL TITLE
    # ============================================
    if trial.get("official_title"):
        st.markdown(f"<div class='trial-official-title'>{trial['official_title']}</div>", unsafe_allow_html=True)

    # ============================================
    # Details Grid (Show only non-empty fields)
    # ============================================
    st.markdown("<div class='detail-grid'>", unsafe_allow_html=True)
    fields = {
        "NCT ID": trial.get("nct_id", "N/A"),
        "Phase": trial.get("phase", "N/A"),
        "Status": trial.get("overall_status", "N/A"),
        "Study Type": trial.get("study_type", "N/A"),
        "Age Group": f"{trial.get('min_age_years', 'N/A')} - {trial.get('max_age_years', 'N/A')} Years",
        "Gender": trial.get("sex", "All"),
        "Conditions": ", ".join(trial.get("conditions", [])) if trial.get("conditions") else None,
        "Locations": ", ".join([loc.get("facility_name", "") + ", " + loc.get("city", "") + (", " + loc.get("country", "") if loc.get("country") else "") for loc in trial.get("locations", [])]) if trial.get("locations") else None,
    }

    for label, value in fields.items():
        if value:  # Only show sections with content
            st.markdown(
                f"""
                <div>
                    <div class='detail-label'>{label}</div>
                    <div class='detail-value'>{value}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown("</div>", unsafe_allow_html=True)

    # ============================================
    # Summaries & Descriptions (Show only non-empty sections)
    # ============================================
    summary_sections = [
        ("Brief Summary", trial.get("brief_summary", "No summary available.")),
        ("Detailed Description", trial.get("detailed_description", "No description available.")),
        ("Inclusion Criteria", trial.get("criteria_inclusion", "N/A")),
        ("Exclusion Criteria", trial.get("criteria_exclusion", "N/A"))
    ]

    for title, content in summary_sections:
        if content and content != "N/A" and content != "No summary available.":  # Skip empty or placeholder content
            st.markdown(f"<div class='summary-title'>{title}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='summary-text'>{content}</div>", unsafe_allow_html=True)

    # BACK BUTTON
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    
    # Use Streamlit's `on_click` function to navigate to the "main" page
    st.button("⬅ Back to Search", on_click=lambda: st.session_state.update(page="main"), key="back_button")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ============================================
# MAIN PAGE — SEARCH UI
# ============================================

st.markdown("<h1 style='color:white;'>🧬 Clinical Trial Finder</h1>", unsafe_allow_html=True)

# ============================================
# PATIENT DETAILS (collapsible)
# ============================================

st.markdown("""
<style>
/* Target the expander container */
section[data-testid="stExpander"] {
    border: none !important;          /* Remove the border */
    box-shadow: none !important;      /* Remove shadow if any */
    background-color: transparent !important; /* Remove background */
    padding: 0 !important;            /* Optional: remove padding */
}

/* Target the expander label text */
section[data-testid="stExpander"] > div > div:first-child {
    font-size: 1.8rem !important;     /* Increase font size */
    font-weight: 700 !important;      /* Make it bold */
    color: white !important;          /* For dark theme */
}
</style>
""", unsafe_allow_html=True)

with st.expander("🧪 PATIENT DETAILS", expanded=False):
    age = st.number_input("Age", min_value=1, max_value=120)
    gender = st.radio("Gender", ["Male", "Female", "All"])
    ecog = st.selectbox("ECOG Performance Status", [0, 1, 2, 3, 4], index=1)
    st.caption("0 = Fully Active, 4 = Bedbound")


# ============================================
# DIAGNOSIS & HISTORY (collapsible)
# ============================================
with st.expander("🧪 DIAGNOSIS & HISTORY", expanded=False):
    condition_input = st.text_input(
        "Primary Diagnosis / Condition",
        placeholder="e.g. Lung Cancer, Skin Cancer"
    )

    # Always accept raw condition text
    conditions_payload = [condition_input] if condition_input else []

    biomarkers = st.multiselect(
        "Genomic Markers", 
        ["EGFR", "HER2", "ALK", "KRAS", "BRAF", "BCR-ABL", "FLT3", "CD19", "ER", "PR"]
    )

    history_input = st.text_area("History / Comorbidities (one per line)")
    history_list = [line.strip() for line in history_input.split("\n") if line.strip()]

    prior_lines = st.number_input("Prior Lines of Therapy", min_value=0, value=0)
    days_since_last_treatment = st.number_input("Days Since Last Treatment", min_value=0, value=30)


# ============================================
# LAB VALUES (multi-add)
# ============================================

LAB_OPTIONS = [
  "EGFR_Gene",
  "ALK_Gene",
  "ROS1_Gene",
  "KRAS_Gene",
  "NRAS_Gene",
  "BRAF_Gene",
  "PIK3CA_Gene",
  "MET_Gene",
  "RET_Gene",
  "NTRK_Gene",
  "BCR_ABL_Gene",
  "FLT3_Gene",
  "NPM1_Gene",
  "IDH1_Gene",
  "IDH2_Gene",
  "JAK2_Gene",
  "TP53_Gene",
  "HER2_Receptor",
  "ER_Status",
  "PR_Status",
  "BRCA1_Gene",
  "BRCA2_Gene",
  "PD_L1_Expression",
  "TMB",
  "MSI_Status",
  "CD19_Marker",
  "CD20_Marker",
  "CD38_Marker",
  "BCMA_Marker",
  "Creatinine_Level",
  "GFR_Level",
  "BUN_Level",
  "Albumin_Level",
  "Protein_Urine",
  "Bilirubin_Level",
  "AST_Level",
  "ALT_Level",
  "ALP_Level",
  "INR_Level",
  "BNP_Level",
  "LVEF_Score",
  "Troponin_Level",
  "CK_MB_Level",
  "Hemoglobin_Level",
  "Hematocrit_Level",
  "Platelet_Count",
  "WBC_Count",
  "ANC_Level",
  "Lymphocyte_Count",
  "Monocyte_Count",
  "Eosinophil_Count",
  "PTT_Level",
  "D_Dimer_Level",
  "Fibrinogen_Level",
  "Cholesterol_Total",
  "LDL_Cholesterol",
  "HDL_Cholesterol",
  "Triglycerides_Level",
  "HbA1c_Level",
  "Glucose_Level",
  "Insulin_Level",
  "TSH_Level",
  "T4_Level",
  "T3_Level",
  "PSA_Level",
  "CEA_Level",
  "CA_125_Level",
  "CA_19_9_Level",
  "AFP_Level",
  "Beta_hCG_Level",
  "CRP_Level",
  "ESR_Level",
  "Sodium_Level",
  "Potassium_Level",
  "Calcium_Level",
  "Magnesium_Level",
  "Phosphate_Level",
  "Chloride_Level",
  "Testosterone_Level",
  "Estradiol_Level",
  "Cortisol_Level",
  "Vitamin_D_Level",
  "Bone_Alkaline_Phosphatase",
  "CTX_Level",
  "Osteocalcin_Level",
  "HIV_Viral_Load",
  "HBV_DNA_Level",
  "HCV_RNA_Level",
  "ANA_Level",
  "RF_Level",
  "Anti_CCP_Level",
  "Lactate_Level",
  "Ammonia_Level",
  "Uric_Acid_Level",
  "Ferritin_Level",
  "Iron_Level",
  "TIBC_Level",
  "B12_Level",
  "Folate_Level"
]

with st.expander("🧪 LAB VALUES", expanded=False):
    # Initialize session state for lab values
    if "lab_values_list" not in st.session_state:
        st.session_state.lab_values_list = [{"lab": None, "value": 0.0}]

    # Render all lab input rows
    for i, entry in enumerate(st.session_state.lab_values_list):
        col_lab, col_val = st.columns([3, 1], gap="small")

        # Compute available options for this row
        used_labs = [lv["lab"] for idx, lv in enumerate(st.session_state.lab_values_list) if idx != i and lv["lab"]]
        options = [lab for lab in LAB_OPTIONS if lab not in used_labs]

        with col_lab:
            selected_lab = st.selectbox(
                "Lab Name",
                options,
                index=options.index(entry["lab"]) if entry["lab"] in options else 0,
                key=f"lab_name_{i}"
            )
            st.session_state.lab_values_list[i]["lab"] = selected_lab

        with col_val:
            val = st.number_input(
                "Value",
                min_value=0.0,
                value=entry.get("value", 0.0),
                format="%.2f",
                key=f"lab_val_{i}"
            )
            st.session_state.lab_values_list[i]["value"] = val

    # Button to add another lab row
    if st.button("Add Another Lab"):
        st.session_state.lab_values_list.append({"lab": None, "value": 0.0})

    # Compose dictionary for payload
    labs = {
        lv["lab"]: lv["value"]
        for lv in st.session_state.lab_values_list
        if lv["lab"] is not None
    }


# ============================================
# BUILD PROFILE PAYLOAD
# ============================================
profile_payload = {
    "age": age,
    "gender": gender.lower(),
    "conditions": conditions_payload,
    "ecog": ecog,
    "biomarkers": biomarkers,
    "history": history_list,
    "labs": labs,
    "prior_lines": prior_lines,
    "days_since_last_treatment": days_since_last_treatment
}

payload = {
    "profile": profile_payload,
    "phase": None,
    "overall_status": None,
    "condition": condition_input if condition_input else None,
    "country": None,
    "bm25_weight": 0.5,
    "feasibility_weight": 0.6
}


# ============================================
# RANK TRIALS
# ============================================
st.markdown("<hr>", unsafe_allow_html=True)

if st.button("Search", use_container_width=True):
    with st.spinner("Searching..."):
        try:
            response = rank_trials(payload)
            hits = response.get("hits", []) if response else []
            st.session_state["results"] = hits
        except Exception as e:
            st.error(f"Backend error: {e}")
            st.session_state["results"] = []


# ============================================
# SEARCH RESULTS
# ============================================


render_results(st.session_state.get("results", []))