import sys
from pathlib import Path
import streamlit as st

# Ensure imports work
frontend_root = Path(__file__).parent.parent.resolve()
if str(frontend_root) not in sys.path:
    sys.path.append(str(frontend_root))

from api_clients.trial_api import rank_trials
from app.ui.results_panel import render_results

# ============================================
# Streamlit Page Config
# ============================================

st.set_page_config(
    page_title="Clinical Trial Engine",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================
# Aesthetic Minimal CSS
# ============================================

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, div, p, span {
    font-family: 'Inter', sans-serif !important;
}

body, .stApp {
    background: linear-gradient(180deg,#0a0a0a 0%, #0d1117 100%);
    color: #e6edf3 !important;
}

/* Main Container */

.block-container {
    max-width: 900px;
    margin: auto;
    padding-top: 8vh;
}

/* Title */

.google-title {
    text-align: center;
    font-size: 3.5rem;
    font-weight: 800;
    margin-bottom: 10px;
    letter-spacing: -1px;
}

/* Subtitle */

.subtitle {
    text-align: center;
    opacity: 0.6;
    margin-bottom: 30px;
}

/* Search Bar */

.stTextInput input {
    background-color: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 14px !important;
    padding: 14px !important;
    color: white !important;
}

/* Dropdown */

.stSelectbox div[data-baseweb="select"] {
    background-color: #0d1117 !important;
    border-radius: 10px !important;
}

/* Buttons */

.stButton button {
    background: linear-gradient(135deg,#4f46e5,#6366f1);
    border: none;
    border-radius: 10px;
    color: white;
    font-weight: 500;
    transition: 0.2s;
}

.stButton button:hover {
    transform: translateY(-1px);
    box-shadow: 0px 4px 14px rgba(79,70,229,0.4);
}

/* Center Button */

.center-button {
    display:flex;
    justify-content:center;
    margin-top:20px;
}

/* Glass Card */

.glass {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 25px;
    margin-top: 20px;
}

</style>
""", unsafe_allow_html=True)


# ============================================
# Session State
# ============================================

if "page" not in st.session_state:
    st.session_state.page = "main"

if "selected_trial" not in st.session_state:
    st.session_state.selected_trial = None

if "advanced" not in st.session_state:
    st.session_state.advanced = False


# ============================================
# TRIAL PAGE
# ============================================

if st.session_state.page == "trial":

    trial = st.session_state.selected_trial

    if not trial:
        st.error("No trial selected.")
        st.button("Back", on_click=lambda: st.session_state.update(page="main"))
        st.stop()

    st.markdown(f"""
    <h1>{trial.get('official_title','')}</h1>
    """, unsafe_allow_html=True)

    render_results([])

    st.button("⬅ Back to Search", on_click=lambda: st.session_state.update(page="main"))

    st.stop()


# ============================================
# HEADER
# ============================================

st.markdown("""
<div class='google-title'>
🧬 Clinical Trial Engine
</div>

<div class='subtitle'>
Find the most relevant trials in seconds
</div>
""", unsafe_allow_html=True)


# ============================================
# SEARCH BAR
# ============================================

col1, col2 = st.columns([10,1])

with col1:
    condition_input = st.text_input(
        "",
        placeholder="Search Clinical Trials...",
        label_visibility="collapsed"
    )

with col2:
    search_clicked = st.button("🔍", use_container_width=True)


# ============================================
# ADVANCED BUTTON (CENTERED)
# ============================================

colA, colB, colC = st.columns([2,2,2])

with colB:
    if st.button("Advanced Search", use_container_width=True):
        st.session_state.advanced = not st.session_state.advanced


# ============================================
# ADVANCED SEARCH
# ============================================

if st.session_state.advanced:


    # PATIENT DETAILS
    st.subheader("Patient Details")

    age = st.number_input("Age", min_value=1, max_value=120)
    gender = st.radio("Gender", ["Male","Female","All"])
    ecog = st.selectbox("ECOG", [0,1,2,3,4], index=1)


    # DIAGNOSIS
    st.subheader("Diagnosis & History")

    biomarkers = st.multiselect(
        "Genomic Markers",
        ["EGFR","HER2","ALK","KRAS","BRAF","FLT3"]
    )

    history_input = st.text_area("History / Comorbidities")

    prior_lines = st.number_input("Prior Lines", min_value=0, value=0)
    days_since_last_treatment = st.number_input(
        "Days Since Last Treatment",
        min_value=0,
        value=30
    )


    # ============================================
    # LAB VALUES
    # ============================================

    st.subheader("Lab Values")

    if "lab_values_list" not in st.session_state:
        st.session_state.lab_values_list = [{"lab": None, "value": 0.0}]

    LAB_OPTIONS = [
        "Creatinine_Level",
        "ALT_Level",
        "AST_Level",
        "Bilirubin_Level",
        "Hemoglobin_Level",
        "Platelet_Count",
        "WBC_Count",
        "Glucose_Level",
        "CRP_Level",
        "Ferritin_Level"
    ]

    for i, entry in enumerate(st.session_state.lab_values_list):

        col_lab, col_val = st.columns([3,1])

        with col_lab:
            selected_lab = st.selectbox(
                "Lab",
                LAB_OPTIONS,
                key=f"lab_name_{i}"
            )

            st.session_state.lab_values_list[i]["lab"] = selected_lab

        with col_val:
            val = st.number_input(
                "Value",
                value=entry.get("value",0.0),
                key=f"lab_val_{i}"
            )

            st.session_state.lab_values_list[i]["value"] = val


    if st.button("Add Another Lab"):
        st.session_state.lab_values_list.append(
            {"lab": None, "value": 0.0}
        )

    labs = {
        lv["lab"]: lv["value"]
        for lv in st.session_state.lab_values_list
        if lv["lab"]
    }

    st.markdown("---")

    # CENTERED SEARCH BUTTON
    colA, colB, colC = st.columns([3,1,3])

    with colB:
        search_bottom = st.button("Search")

    st.markdown("</div>", unsafe_allow_html=True)

else:
    age = 50
    gender = "All"
    ecog = 1
    biomarkers = []
    history_input = ""
    prior_lines = 0
    days_since_last_treatment = 30
    labs = {}
    search_bottom = False


# ============================================
# PAYLOAD
# ============================================

profile_payload = {
    "age": age,
    "gender": gender.lower(),
    "conditions": [condition_input] if condition_input else [],
    "ecog": ecog,
    "biomarkers": biomarkers,
    "history": [history_input] if history_input else [],
    "labs": labs,
    "prior_lines": prior_lines,
    "days_since_last_treatment": days_since_last_treatment
}

payload = {
    "profile": profile_payload,
    "phase": None,
    "overall_status": None,
    "condition": condition_input,
    "country": None,
    "bm25_weight": 0.5,
    "feasibility_weight": 0.6
}


# ============================================
# SEARCH
# ============================================

if search_clicked or search_bottom:
    with st.spinner("Searching trials..."):
        response = rank_trials(payload)
        hits = response.get("hits", []) if response else []
        st.session_state["results"] = hits


# ============================================
# RESULTS
# ============================================

render_results(st.session_state.get("results", []))