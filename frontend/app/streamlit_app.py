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

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _v(v, fallback="N/A"):
        return v if v not in (None, "", [], {}) else fallback

    def _parse_elig(raw):
        if not raw:
            return "", ""
        rl = raw.lower()
        ii, ei = rl.find("inclusion criteria"), rl.find("exclusion criteria")
        if ii == -1 and ei == -1:
            return raw.strip(), ""
        if ii != -1 and ei != -1:
            return raw[ii:ei].strip(), raw[ei:].strip()
        if ii != -1:
            return raw[ii:].strip(), ""
        return "", raw[ei:].strip()

    # ── Extract fields ────────────────────────────────────────────────────────
    elig_mod = trial.get("eligibility") or {}
    if not isinstance(elig_mod, dict):
        elig_mod = {}

    title   = _v(trial.get("official_title") or trial.get("title"))
    phase   = _v(trial.get("phase"))
    status  = _v(trial.get("overall_status"))
    nct_id  = trial.get("nct_id", "")

    min_age = _v(trial.get("minimum_age") or trial.get("min_age") or elig_mod.get("minimumAge"))
    max_age = _v(trial.get("maximum_age") or trial.get("max_age") or elig_mod.get("maximumAge"))
    sex     = _v(trial.get("sex") or trial.get("gender") or elig_mod.get("sex"))
    brief   = _v(trial.get("brief_summary") or trial.get("description"), "")

    inc_raw = trial.get("inclusion_criteria") or trial.get("inclusion") or ""
    exc_raw = trial.get("exclusion_criteria") or trial.get("exclusion") or ""
    if not inc_raw and not exc_raw:
        raw_block = trial.get("eligibility_criteria") or elig_mod.get("eligibilityCriteria") or ""
        inc_raw, exc_raw = _parse_elig(raw_block)

    locs_raw = trial.get("locations") or trial.get("location") or []
    if isinstance(locs_raw, list):
        loc_parts = []
        for loc in locs_raw[:5]:
            if isinstance(loc, dict):
                chunk = ", ".join(filter(None, [
                    loc.get("facility") or loc.get("name"),
                    loc.get("city"),
                    loc.get("country"),
                ]))
                if chunk:
                    loc_parts.append(chunk)
            elif isinstance(loc, str):
                loc_parts.append(loc)
        location_lines = "\n".join(f"• {p}" for p in loc_parts) if loc_parts else "N/A"
    else:
        location_lines = str(locs_raw) if locs_raw else "N/A"

    # ── Render ────────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    .detail-card {
        background:#111; border:1px solid #2a2a3a;
        border-radius:18px; padding:32px 36px; margin-top:8px;
    }
    .d-title  { color:#fff; font-size:1.3rem; font-weight:700; margin:0 0 8px 0; line-height:1.4; }
    .d-badges { color:#9ca3af; font-size:14px; margin-bottom:0; }
    .d-accent { color:#818cf8; font-family:monospace; }
    .d-label  { color:#6366f1; font-size:11px; font-weight:700;
                text-transform:uppercase; letter-spacing:.08em; margin:22px 0 5px 0; }
    .d-text   { color:#cbd5e1; font-size:14px; line-height:1.75; margin:0; }
    .d-hr     { border:none; border-top:1px solid #1e2330; margin:20px 0; }
    </style>
    """, unsafe_allow_html=True)

    nct_badge = f"&nbsp;•&nbsp;<span class='d-accent'>{nct_id}</span>" if nct_id else ""

    st.markdown(f"""
    <div class="detail-card">
        <p class="d-title">{title}</p>
        <p class="d-badges">Phase {phase} &nbsp;•&nbsp; {status}{nct_badge}</p>
        <hr class="d-hr">

        <p class="d-label">Eligibility</p>
        <p class="d-text">
            Min Age: <b style="color:#e2e8f0">{min_age}</b>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Max Age: <b style="color:#e2e8f0">{max_age}</b>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Sex: <b style="color:#e2e8f0">{sex}</b>
        </p>

        <p class="d-label">Summary</p>
        <p class="d-text">{brief}</p>

        <p class="d-label">Inclusion Criteria</p>
        <p class="d-text" style="white-space:pre-wrap">{inc_raw or "N/A"}</p>

        <p class="d-label">Exclusion Criteria</p>
        <p class="d-text" style="white-space:pre-wrap">{exc_raw or "N/A"}</p>

        <p class="d-label">Location(s)</p>
        <p class="d-text" style="white-space:pre-wrap">{location_lines}</p>
    </div>
    """, unsafe_allow_html=True)

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