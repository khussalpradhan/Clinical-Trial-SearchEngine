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
    page_title="TrialMatch+",
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

if "show_advanced" not in st.session_state:
    st.session_state.show_advanced = False


# ============================================
# TRIAL DETAIL PAGE
# ============================================

if st.session_state.page == "trial":

    trial = st.session_state.selected_trial

    if not trial:
        st.error("No trial selected.")
        st.button("Back", on_click=lambda: st.session_state.update(page="main"))
        st.stop()

    st.button("⬅ Back to Search", on_click=lambda: st.session_state.update(page="main"))

    st.markdown(f"<h1 style='color:white;'>{trial.get('official_title') or trial.get('title', 'Untitled Study')}</h1>", unsafe_allow_html=True)

    # ── Status / Phase / NCT ID badges ──────────────────────────────────────
    nct_id  = trial.get("nct_id", "")
    phase   = trial.get("phase", "N/A")
    status  = trial.get("overall_status", "N/A")

    st.markdown(
        f"<p style='color:#aaa; font-size:15px;'>NCT ID: <b style='color:white'>{nct_id}</b> &nbsp;|&nbsp; "
        f"Phase: <b style='color:white'>{phase}</b> &nbsp;|&nbsp; "
        f"Status: <b style='color:white'>{status}</b></p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Brief Summary ────────────────────────────────────────────────────────
    brief = trial.get("brief_summary") or trial.get("description", "")
    if brief:
        st.markdown("### Summary")
        st.markdown(f"<p style='color:#ccc; line-height:1.7'>{brief}</p>", unsafe_allow_html=True)

    # ── Detailed Description ─────────────────────────────────────────────────
    detailed = trial.get("detailed_description", "")
    if detailed:
        with st.expander("Detailed Description"):
            st.markdown(f"<p style='color:#ccc; line-height:1.7'>{detailed}</p>", unsafe_allow_html=True)

    # ── Eligibility ──────────────────────────────────────────────────────────
    eligibility = trial.get("eligibility_criteria") or trial.get("eligibility", "")
    if eligibility:
        st.markdown("### Eligibility Criteria")
        st.markdown(f"<p style='color:#ccc; line-height:1.7; white-space:pre-wrap'>{eligibility}</p>", unsafe_allow_html=True)

    # ── Locations ────────────────────────────────────────────────────────────
    locations = trial.get("locations", [])
    if locations:
        st.markdown("### Locations")
        for loc in locations[:10]:
            if isinstance(loc, dict):
                facility = loc.get("facility", "")
                city     = loc.get("city", "")
                country  = loc.get("country", "")
                st.markdown(f"- **{facility}** — {city}, {country}")
            else:
                st.markdown(f"- {loc}")

    # ── Interventions ────────────────────────────────────────────────────────
    interventions = trial.get("interventions", [])
    if interventions:
        st.markdown("### Interventions")
        for iv in interventions:
            if isinstance(iv, dict):
                st.markdown(f"- **{iv.get('type','')}**: {iv.get('name','')}")
            else:
                st.markdown(f"- {iv}")

    # ── Contact ──────────────────────────────────────────────────────────────
    contact = trial.get("contact") or {}
    if contact:
        st.markdown("### Contact")
        name  = contact.get("name", "")
        email = contact.get("email", "")
        phone = contact.get("phone", "")
        if name:  st.markdown(f"**Name:** {name}")
        if email: st.markdown(f"**Email:** {email}")
        if phone: st.markdown(f"**Phone:** {phone}")

    # ── Raw dump fallback (dev helper) ───────────────────────────────────────
    with st.expander("Raw trial data (debug)"):
        st.json(trial)

    st.stop()


# ============================================
# MAIN SEARCH PAGE
# ============================================

st.markdown("""
<div class='google-title'>
🧬 TrialMatch+
</div>

<div class='subtitle'>
Find the most relevant trials in seconds
</div>
""", unsafe_allow_html=True)


# ============================================
# SEARCH BAR
# ============================================

condition_input = st.text_input(
    "",
    placeholder="Search Clinical Trials...",
    label_visibility="collapsed"
)


# ============================================
# SEARCH  +  ADVANCED  BUTTONS (centered, equal width)
# ============================================

_, col_search, col_adv, _ = st.columns([1, 2, 2, 1])

with col_search:
    search_clicked = st.button("Search", use_container_width=True)

with col_adv:
    if st.button("⚙ Advanced Search", use_container_width=True):
        st.session_state.show_advanced = not st.session_state.show_advanced


# ============================================
# ADVANCED SEARCH PANEL
# ============================================

search_bottom = False   # will be set inside the expander if user hits Search there

if st.session_state.show_advanced:

    st.markdown("---")

    # PATIENT DETAILS
    st.subheader("Patient Details")

    age    = st.number_input("Age", min_value=1, max_value=120, value=50)
    gender = st.radio("Gender", ["Male", "Female", "All"])
    ecog   = st.selectbox("ECOG", [0, 1, 2, 3, 4], index=1)

    # DIAGNOSIS
    st.subheader("Diagnosis & History")

    biomarkers = st.multiselect(
        "Genomic Markers",
        ["EGFR", "HER2", "ALK", "KRAS", "BRAF", "FLT3"]
    )

    history_input          = st.text_area("History / Comorbidities")
    prior_lines            = st.number_input("Prior Lines", min_value=0, value=0)
    days_since_last_treatment = st.number_input(
        "Days Since Last Treatment", min_value=0, value=30
    )

    # LAB VALUES
    st.subheader("Lab Values")

    if "lab_values_list" not in st.session_state:
        st.session_state.lab_values_list = [{"lab": None, "value": 0.0}]

    LAB_OPTIONS = [
        "Creatinine_Level", "ALT_Level", "AST_Level", "Bilirubin_Level",
        "Hemoglobin_Level", "Platelet_Count", "WBC_Count",
        "Glucose_Level", "CRP_Level", "Ferritin_Level"
    ]

    for i, entry in enumerate(st.session_state.lab_values_list):
        col_lab, col_val = st.columns([3, 1])
        with col_lab:
            selected_lab = st.selectbox("Lab", LAB_OPTIONS, key=f"lab_name_{i}")
            st.session_state.lab_values_list[i]["lab"] = selected_lab
        with col_val:
            val = st.number_input("Value", value=entry.get("value", 0.0), key=f"lab_val_{i}")
            st.session_state.lab_values_list[i]["value"] = val

    if st.button("Add Another Lab"):
        st.session_state.lab_values_list.append({"lab": None, "value": 0.0})

    labs = {
        lv["lab"]: lv["value"]
        for lv in st.session_state.lab_values_list
        if lv["lab"]
    }

    st.markdown("---")

    colA, colB, colC = st.columns([3, 1, 3])
    with colB:
        search_bottom = st.button("Search  ", use_container_width=True)   # trailing space makes key unique

else:
    # Default / empty values when advanced panel is hidden
    age                       = 0
    gender                    = "all"
    ecog                      = 0
    biomarkers                = []
    history_input             = ""
    prior_lines               = 0
    days_since_last_treatment = 0
    labs                      = {}


# ============================================
# BUILD PAYLOAD
# ============================================

if st.session_state.show_advanced:
    profile_payload = {
        "age":                      age,
        "gender":                   gender.lower(),
        "conditions":               [condition_input] if condition_input else [],
        "ecog":                     ecog,
        "biomarkers":               biomarkers,
        "history":                  [history_input] if history_input else [],
        "labs":                     labs,
        "prior_lines":              prior_lines,
        "days_since_last_treatment": days_since_last_treatment,
    }
    payload = {
        "profile":             profile_payload,
        "phase":               None,
        "overall_status":      None,
        "condition":           condition_input,
        "country":             None,
        "bm25_weight":         0.5,
        "feasibility_weight":  0.6,
    }
else:
    # Simple search — only the condition string matters
    payload = {
        "profile": {
            "age":                       None,
            "gender":                    None,
            "conditions":                [condition_input] if condition_input else [],
            "ecog":                      None,
            "biomarkers":                [],
            "history":                   [],
            "labs":                      {},
            "prior_lines":               None,
            "days_since_last_treatment": None,
        },
        "phase":              None,
        "overall_status":     None,
        "condition":          condition_input,
        "country":            None,
        "bm25_weight":        0.5,
        "feasibility_weight": 0.0,   # no feasibility scoring without patient data
    }


# ============================================
# RUN SEARCH
# ============================================

if (search_clicked or search_bottom) and condition_input:
    with st.spinner("Searching trials..."):
        response = rank_trials(payload)
        hits     = response.get("hits", []) if response else []
        st.session_state["results"] = hits
elif (search_clicked or search_bottom) and not condition_input:
    st.warning("Please enter a condition or keyword to search.")


# ============================================
# RESULTS
# ============================================

render_results(st.session_state.get("results", []))