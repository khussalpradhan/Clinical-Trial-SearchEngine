import sys
from pathlib import Path
import streamlit as st
frontend_root = Path(__file__).parent.parent.resolve()
if str(frontend_root) not in sys.path:
    sys.path.append(str(frontend_root))

from api_clients.trial_api import rank_trials
from app.ui.results_panel import render_results

# -------------------------
# Streamlit Page Config
# -------------------------
st.set_page_config(
    page_title="Clinical Trial Finder",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------
# Global Dark Theme CSS
# -------------------------
st.markdown("""
<style>
body, .stApp {
    background-color: #000 !important; 
    color: white !important; 
    font-family: 'Inter', sans-serif;
}
.block-container {padding-top: 2rem; max-width: 1150px;}
.section-title {font-size:1.5rem; font-weight:700; color:white; margin-bottom:10px; margin-top:20px;}
.stTextInput>div>div>input, 
.stNumberInput>div>div>input, 
.stTextArea>div>div>textarea, 
.stSelectbox>div>div>div>div {
    max-width: 600px !important;
}
.stRadio>div>div, .stMultiSelect>div>div {
    max-width: 600px !important;
}
hr {border-color:#333;}
.button-primary {background-color:#222 !important; color:white !important; font-weight:600;}
.trial-card {margin-bottom:15px; padding:20px; border-radius:12px; border:1px solid #222; background:#111;}
.trial-card h3, .trial-card p {color:white;}
</style>
""", unsafe_allow_html=True)

# -------------------------
# Page Navigation
# -------------------------
page = st.query_params.get("page", ["main"])[0]

# -------------------------
# Trial Details Page
# -------------------------
if page == "trial":
    nct_id = st.query_params.get("nct_id", [""])[0]

    # Fetch trial from session_state (from ranked results)
    results = st.session_state.get("results", [])
    trial = next((t for t in results if t.get("nct_id") == nct_id), None)

    if trial:
        st.markdown(f"<h1 style='color:white;'>{trial.get('title','Untitled')}</h1>", unsafe_allow_html=True)

        st.markdown(f"""
        <div style="margin-top:20px;">
            <p><strong>NCT ID:</strong> {trial.get('nct_id','N/A')}</p>
            <p><strong>Phase:</strong> {trial.get('phase','N/A')}</p>
            <p><strong>Status:</strong> {trial.get('overall_status','N/A')}</p>
            <p><strong>Study Type:</strong> {trial.get('study_type','N/A')}</p>
            <p><strong>Conditions:</strong> {', '.join(trial.get('conditions',[]))}</p>
            <p><strong>Locations:</strong> {', '.join(trial.get('locations',[]))}</p>
            <hr>
            <h3>Brief Summary</h3>
            <p>{trial.get('brief_summary','No summary available.')}</p>
        </div>
        """, unsafe_allow_html=True)

    else:
        st.warning("Trial not found or results expired. Go back to search.")

    if st.button("⬅ Back to Search"):
        st.query_params.clear()
        st.experimental_rerun()

# -------------------------
# Main Page: Search + Form
# -------------------------
else:
    st.markdown("<h1 style='color:white;'>🧬 Clinical Trial Finder</h1>", unsafe_allow_html=True)

    # -------------------------
    # Patient Details Section
    # -------------------------
    st.markdown('<div class="section-title">PATIENT DETAILS</div>', unsafe_allow_html=True)
    age = st.number_input("Age", min_value=1, max_value=120)
    gender = st.radio("Gender", ["Male", "Female", "All"])
    ecog = st.selectbox("ECOG Performance Status", [0,1,2,3,4], index=1)
    st.caption("0 = Fully Active, 4 = Bedbound")

    # -------------------------
    # Diagnosis & History Section
    # -------------------------
    st.markdown('<div class="section-title">DIAGNOSIS & HISTORY</div>', unsafe_allow_html=True)
    ALLOWED_CONDITIONS = [
        "NSCLC","Breast_Cancer","Heart_Failure","Chronic_Kidney_Disease",
        "Respiratory_Failure","Liver_Failure","Leukemia","Prostate_Cancer",
        "Skin_Cancer","Cervical_Cancer","Bone_Cancer"
    ]
    condition_input = st.text_input("Primary Diagnosis / Condition", placeholder="e.g. Lung Cancer, Skin Cancer")
    condition_normalized = condition_input.strip().replace(" ","_") if condition_input else ""
    if condition_normalized and condition_normalized not in ALLOWED_CONDITIONS:
        st.error(f"Invalid condition: {condition_input}. Allowed: {', '.join(ALLOWED_CONDITIONS)}")
        conditions_payload = []
    else:
        conditions_payload = [condition_normalized] if condition_normalized else []

    biomarkers = st.multiselect(
        "Genomic Markers / Status",
        ["EGFR","HER2","ALK","KRAS","BRAF","BCR-ABL","FLT3","CD19","ER","PR"]
    )
    history_input = st.text_area("History / Comorbidities (one per line)")
    history_list = [line.strip() for line in history_input.split("\n") if line.strip()]
    prior_lines = st.number_input("Prior Lines of Therapy", min_value=0, value=0)
    days_since_last_treatment = st.number_input("Days Since Last Treatment", min_value=0, value=30)

    # -------------------------
    # Lab Values Section
    # -------------------------
    st.markdown('<div class="section-title">LAB VALUES</div>', unsafe_allow_html=True)
    creatinine = st.number_input("Creatinine (mg/dL)", min_value=0.0, value=0.0)
    gfr = st.number_input("GFR (mL/min)", min_value=0.0, value=0.0)
    bilirubin = st.number_input("Bilirubin (mg/dL)", min_value=0.0, value=0.0)
    ast = st.number_input("AST (U/L)", min_value=0.0, value=0.0)
    alt = st.number_input("ALT (U/L)", min_value=0.0, value=0.0)
    platelets = st.number_input("Platelet Count (10^9/L)", min_value=0.0, value=0.0)
    hemoglobin = st.number_input("Hemoglobin (g/dL)", min_value=0.0, value=0.0)
    psa = st.number_input("PSA (ng/mL)", min_value=0.0, value=0.0)

    labs = {k:v for k,v in {"Creatinine":creatinine,"GFR":gfr,"Bilirubin":bilirubin,"AST":ast,"ALT":alt,
                            "Platelet_Count":platelets,"Hemoglobin":hemoglobin,"PSA":psa}.items() if v>0}

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
        "bm25_weight":0.5,
        "feasibility_weight":0.6
    }

    st.markdown("<hr>", unsafe_allow_html=True)
    if st.button("Rank Trials", use_container_width=True):
        with st.spinner("Ranking trials…"):
            try:
                response = rank_trials(payload)
                hits = response.get("hits", []) if response else []
                st.session_state["results"] = hits
            except Exception as e:
                st.error(f"Backend error: {e}")
                st.session_state["results"] = []

    st.markdown("<h2 style='color:white;margin-top:20px;margin-bottom:20px'>SEARCH RESULTS</h2>", unsafe_allow_html=True)
    render_results(st.session_state.get("results", []))
