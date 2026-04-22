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

    # Properly extract from backend TrialDetail fields: min_age_years, max_age_years, sex
    min_age = trial.get("min_age_years") if trial.get("min_age_years") is not None else trial.get("minimum_age")
    max_age = trial.get("max_age_years") if trial.get("max_age_years") is not None else trial.get("maximum_age")
    sex_val = trial.get("sex") if trial.get("sex") is not None else trial.get("gender")

    min_age = _v(min_age)
    max_age = _v(max_age)
    sex     = _v(sex_val)
    
    brief   = _v(trial.get("brief_summary") or trial.get("description"), "")

    inc_raw = trial.get("criteria_inclusion") or trial.get("inclusion_criteria") or ""
    exc_raw = trial.get("criteria_exclusion") or trial.get("exclusion_criteria") or ""
    if not inc_raw and not exc_raw:
        raw_block = trial.get("eligibility_criteria_raw") or trial.get("eligibility_criteria") or elig_mod.get("eligibilityCriteria") or ""
        inc_raw, exc_raw = _parse_elig(raw_block)

    # ── Render with native Streamlit widgets (no custom CSS classes) ─────────

    st.markdown(f"## {title}")
    st.caption(f"Phase {phase}  •  {status}" + (f"  •  {nct_id}" if nct_id else ""))
    st.divider()

    # Custom HTML for metrics so they are bright and clear (not grayed out)
    st.markdown(f"""
    <div style="display: flex; gap: 20px; margin-bottom: 20px;">
        <div style="flex: 1; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 15px; text-align: center;">
            <div style="color: #9ca3af; font-size: 14px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px;">Min Age</div>
            <div style="color: white; font-size: 28px; font-weight: 700; margin-top: 5px;">{min_age}</div>
        </div>
        <div style="flex: 1; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 15px; text-align: center;">
            <div style="color: #9ca3af; font-size: 14px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px;">Max Age</div>
            <div style="color: white; font-size: 28px; font-weight: 700; margin-top: 5px;">{max_age}</div>
        </div>
        <div style="flex: 1; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 15px; text-align: center;">
            <div style="color: #9ca3af; font-size: 14px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px;">Sex</div>
            <div style="color: white; font-size: 28px; font-weight: 700; margin-top: 5px;">{sex}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### Summary")
    st.write(brief if brief else "N/A")

    st.divider()

    st.markdown("<h4 style='color: #e6edf3; margin-top: 30px; margin-bottom: 15px; font-weight: 600; font-size: 18px;'>Inclusion Criteria</h4>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style='background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; padding: 20px; color: #b1bac4; font-size: 14px; line-height: 1.7; white-space: pre-wrap; font-family: "Inter", sans-serif;'>{inc_raw if inc_raw else 'N/A'}</div>
    """, unsafe_allow_html=True)

    st.markdown("<h4 style='color: #e6edf3; margin-top: 30px; margin-bottom: 15px; font-weight: 600; font-size: 18px;'>Exclusion Criteria</h4>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style='background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; padding: 20px; color: #b1bac4; font-size: 14px; line-height: 1.7; white-space: pre-wrap; font-family: "Inter", sans-serif;'>{exc_raw if exc_raw else 'N/A'}</div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
    st.markdown("#### Location(s)")
    locs_raw2 = trial.get("locations") or trial.get("location") or []
    loc_lines = []
    if isinstance(locs_raw2, list):
        for loc in locs_raw2[:5]:
            if isinstance(loc, dict):
                chunk = ", ".join(filter(None, [
                    loc.get("facility") or loc.get("name"),
                    loc.get("city"),
                    loc.get("country"),
                ]))
                if chunk:
                    loc_lines.append(chunk)
            elif isinstance(loc, str):
                loc_lines.append(loc)
    elif locs_raw2:
        loc_lines.append(str(locs_raw2))

    if loc_lines:
        for line in loc_lines:
            st.write(f"• {line}")
    else:
        st.write("N/A")

    st.divider()
    st.button("⬅ Back to Search", on_click=lambda: st.session_state.update(page="main"), key="back_bottom")

    st.stop()


# ============================================
# MAIN SEARCH PAGE
# ============================================

st.markdown("""
<div class='google-title'>
TrialMatch+
</div>

<div class='subtitle'>
Find the most relevant trials in seconds
</div>
""", unsafe_allow_html=True)


# ============================================
# SEARCH BAR
# ============================================

def trigger_search_callback():
    st.session_state.do_search = True

condition_input = st.text_input(
    "",
    placeholder="Search Clinical Trials...",
    label_visibility="collapsed",
    on_change=trigger_search_callback
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

if st.session_state.get("do_search", False):
    search_clicked = True
    st.session_state.do_search = False


# ============================================
# ADVANCED SEARCH PANEL
# ============================================

search_bottom = False   # will be set inside the expander if user hits Search there

if st.session_state.show_advanced:

    st.markdown("---")

    # PATIENT DETAILS
    st.subheader("Patient Details")

    age    = st.number_input("Age", min_value=1, max_value=120, value=None, placeholder="Enter age...")
    gender = st.radio("Gender", ["Male", "Female", "All"], index=None)
    ecog   = st.selectbox("ECOG", [0, 1, 2, 3, 4], index=None, placeholder="Select ECOG status...")

    # DIAGNOSIS
    st.subheader("Diagnosis & History")

    biomarkers = st.multiselect(
        "Genomic Markers",
        ["EGFR", "HER2", "ALK", "KRAS", "BRAF", "FLT3"]
    )

    history_input          = st.text_area("History / Comorbidities", placeholder="e.g. Hypertension, previous stroke...")
    prior_lines            = st.number_input("Prior Lines", min_value=0, value=None, placeholder="Number of prior treatments...")
    days_since_last_treatment = st.number_input(
        "Days Since Last Treatment", min_value=0, value=None, placeholder="e.g. 30, 45, 90..."
    )

    # LAB VALUES
    st.subheader("Lab Values")

    if "lab_values_list" not in st.session_state:
        st.session_state.lab_values_list = [{"lab": None, "value": None}]

    LAB_OPTIONS = [
        "Creatinine_Level", "ALT_Level", "AST_Level", "Bilirubin_Level",
        "Hemoglobin_Level", "Platelet_Count", "WBC_Count",
        "Glucose_Level", "CRP_Level", "Ferritin_Level"
    ]

    for i, entry in enumerate(st.session_state.lab_values_list):
        col_lab, col_val = st.columns([3, 1])
        with col_lab:
            selected_lab = st.selectbox("Lab", LAB_OPTIONS, index=None, placeholder="Select a Lab...", key=f"lab_name_{i}")
            st.session_state.lab_values_list[i]["lab"] = selected_lab
        with col_val:
            val = st.number_input("Value", value=entry.get("value", None), placeholder="0.00", key=f"lab_val_{i}")
            st.session_state.lab_values_list[i]["value"] = val

    if st.button("Add Another Lab"):
        st.session_state.lab_values_list.append({"lab": None, "value": None})
        st.rerun()

    labs = {
        lv["lab"]: lv["value"]
        for lv in st.session_state.lab_values_list
        if lv["lab"] is not None and lv["value"] is not None
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
        "gender":                   gender.lower() if gender else None,
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