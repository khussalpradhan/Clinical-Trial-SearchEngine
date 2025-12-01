import sys
from pathlib import Path
import streamlit as st
frontend_root = Path(__file__).parent.parent.resolve()
if str(frontend_root) not in sys.path:
    sys.path.append(str(frontend_root))


from api_clients.trial_api import rank_trials

from app.ui.search_bar import render_search_bar
from app.ui.results_panel import render_results

# Add frontend root to path

# -------------------------
# Streamlit Page Config
# -------------------------
st.set_page_config(
    page_title="Clinical Trial Finder",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Global dark theme
st.markdown("""
    <style>
        body, .stApp {
            background-color: #000000 !important;
            color: white !important;
            font-family: 'Inter', sans-serif;
        }
    </style>
""", unsafe_allow_html=True)

# -------------------------
# Header
# -------------------------
st.markdown("""
<h1 style="
    color:white;
    font-weight:700;
    font-size:46px;
    letter-spacing:-1px;
">🧬 Clinical Trial Finder</h1>
""", unsafe_allow_html=True)

# -------------------------
# Patient Profile Form
# -------------------------
st.markdown("<h2 style='color:white;'>Patient Profile</h2>", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    age = st.number_input("Age", min_value=1, max_value=120, value=65)
    gender = st.radio("Gender", ["Male", "Female", "All"]) 
    ecog = st.selectbox("ECOG Performance Status", [0, 1, 2, 3, 4], index=1)
    st.caption("0 = Fully Active, 4 = Bedbound")

with col2:
    ALLOWED_CONDITIONS = [
        "NSCLC", "Breast_Cancer", "Heart_Failure", "Chronic_Kidney_Disease",
        "Respiratory_Failure", "Liver_Failure", "Leukemia", "Prostate_Cancer",
        "Skin_Cancer", "Cervical_Cancer", "Bone_Cancer"
    ]

    condition_input = st.text_input(
        "Primary Diagnosis / Condition",
        placeholder="e.g. Lung Cancer, Skin Cancer"
    )

    condition_normalized = condition_input.strip().replace(" ", "_") if condition_input else ""
    if condition_normalized and condition_normalized not in ALLOWED_CONDITIONS:
        st.error(f"Invalid condition: '{condition_input}'. Allowed: {', '.join(ALLOWED_CONDITIONS)}")
        conditions_payload = []
    else:
        conditions_payload = [condition_normalized] if condition_normalized else []

    biomarkers = st.multiselect(
        "Genomic Markers / Status",
        ["EGFR", "HER2", "ALK", "KRAS", "BRAF", "BCR-ABL",
         "FLT3", "CD19", "ER", "PR"]
    )

    history_input = st.text_area("History / Comorbidities", placeholder="Enter one per line")
    history_list = [line.strip() for line in history_input.split("\n") if line.strip()]
    prior_lines = st.number_input("Prior Lines of Therapy", min_value=0, value=0)
    days_since_last_treatment = st.number_input("Days Since Last Treatment", min_value=0, value=30)

with col3:
    st.subheader("Lab Values")
    creatinine = st.number_input("Creatinine (mg/dL)", min_value=0.0, value=0.0)
    gfr = st.number_input("GFR (mL/min)", min_value=0.0, value=0.0)
    bilirubin = st.number_input("Bilirubin (mg/dL)", min_value=0.0, value=0.0)
    ast = st.number_input("AST (U/L)", min_value=0.0, value=0.0)
    alt = st.number_input("ALT (U/L)", min_value=0.0, value=0.0)
    platelets = st.number_input("Platelet Count (10^9/L)", min_value=0.0, value=0.0)
    hemoglobin = st.number_input("Hemoglobin (g/dL)", min_value=0.0, value=0.0)
    psa = st.number_input("PSA (ng/mL)", min_value=0.0, value=0.0)

labs = {
    k: v for k, v in {
        "Creatinine": creatinine,
        "GFR": gfr,
        "Bilirubin": bilirubin,
        "AST": ast,
        "ALT": alt,
        "Platelet_Count": platelets,
        "Hemoglobin": hemoglobin,
        "PSA": psa
    }.items() if v > 0
}

# Final payload
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
    "condition": condition_normalized if condition_normalized else None,
    "country": None,
    "bm25_weight": 0.5,
    "feasibility_weight": 0.6
}

# Rank button
st.markdown("<hr style='border-color:#333;'>", unsafe_allow_html=True)

if st.button("Rank Trials", use_container_width=True):
    with st.spinner("Ranking trials…"):
        try:
            response = rank_trials(payload)
            hits = response.get("hits", []) if response else []
            st.session_state["results"] = hits
        except Exception as e:
            st.error(f"Backend error: {e}")
            st.session_state["results"] = []

# Results Panel
st.markdown("<h2 style='color:white;'>Search Results</h2>", unsafe_allow_html=True)
render_results(st.session_state.get("results", []))
