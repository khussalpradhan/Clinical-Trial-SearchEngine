import sys
from pathlib import Path
import streamlit as st

# Ensure imports work
frontend_root = Path(__file__).parent.parent.resolve()
if str(frontend_root) not in sys.path:
    sys.path.append(str(frontend_root))

from api_clients.trial_api import rank_trials
from app.ui.results_panel import render_results


st.set_page_config(
    page_title="Clinical Trial Finder",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
 @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');

html, body, div, p {
    font-family: 'Inter', sans-serif !important;
}
body, .stApp {
    background-color: #000 !important; 
    color: white !important; 
    font-family: 'Inter', sans-serif;
}
.block-container {padding-top: 2rem; max-width: 1150px;}
.section-title {font-size:1.5rem; font-weight:700; color:white; margin-bottom:10px; margin-top:20px;}
.trial-card {margin-bottom:15px; padding:20px; border-radius:12px; border:1px solid #222; background:#111;}
.trial-card h3, .trial-card p {color:white;}
</style>
""", unsafe_allow_html=True)

# ============================================
# Session State Navigation
# ============================================
if "page" not in st.session_state:
    st.session_state.page = "main"

if "selected_trial" not in st.session_state:
    st.session_state.selected_trial = None



if st.session_state.page == "trial":
    
    
    trial = st.session_state.selected_trial

    if not trial:
        st.error("No trial selected.")
        st.button("Back to Search", on_click=lambda: st.session_state.update(page="main"))
        st.stop()

    
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');

        html, body, div, p {
            font-family: 'Inter', sans-serif !important;
        }

        .trial-container {
            background-color: #111;
            border: 1px solid #222;
            padding: 35px;
            border-radius: 16px;
            margin-top: 25px;
        }

        .trial-title {
            font-size: 2.8rem;
            font-weight: 800;
            color: white;
            margin-bottom: 30px;
            line-height: 1.2;
            letter-spacing: -0.5px;
        }

        .detail-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px 40px;
            margin-bottom: 25px;
        }

        .detail-label {
            font-size: 1.3rem;
            color: #fff;
            font-weight: 700;
            text-transform: uppercase;
            margin-bottom: 12px;
            margin-top: 8px;
        }

        .detail-value {
            font-size: 0.9rem;
            color: #fff;
            font-weight: 500;
            margin-bottom: 4px;
        }

        .summary-title {
            font-size: 1.3rem;
            font-weight: 700;
            color: #eee;
            margin-top: 30px;
            margin-bottom: 10px;
        }

        .summary-text {
            font-size: 1.05rem;
            color: #ccc;
            line-height: 1.65;
        }

        .back-btn {
            background-color: #222 !important;
            color: white !important;
            padding: 10px 18px !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            border: 1px solid #333 !important;
            margin-top: 25px;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <script>
        window.parent.document.querySelector('.main').scrollTo(0, 0);
    </script>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <script>
    // Allow Streamlit DOM to finish rendering then scroll
    setTimeout(function() {
        window.scrollTo({top: 0, behavior: 'instant'});
    }, 50);
    </script>
    """, unsafe_allow_html=True)

    
    
    st.markdown(f"<div class='trial-title'>{trial.get('title','Untitled')}</div>", unsafe_allow_html=True)

    

    st.markdown("<div class='detail-grid'>", unsafe_allow_html=True)

    fields = {
        "NCT ID": trial.get("nct_id", "N/A"),
        "Phase": trial.get("phase", "N/A"),
        "Status": trial.get("overall_status", "N/A"),
        "Study Type": trial.get("study_type", "N/A"),
        "Conditions": ", ".join(trial.get("conditions", [])),
        "Locations": ", ".join(trial.get("locations", [])),
    }

    for label, value in fields.items():
        st.markdown(
            f"""
            <div>
                <div class='detail-label'>{label}</div>
                <div class='detail-value'>{value}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end grid

    # --------------------------------------------------------------------
    # Summary Section
    # --------------------------------------------------------------------
    st.markdown("<div class='summary-title'>Brief Summary</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='summary-text'>{trial.get('brief_summary','No summary available.')}</div>",
        unsafe_allow_html=True
    )


    # --------------------------------------------------------------------
    # BACK BUTTON
    # --------------------------------------------------------------------
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    st.button("⬅ Back to Search", key="back_btn", on_click=lambda: st.session_state.update(page="main"))
    st.stop()


# ============================================
# MAIN PAGE — SEARCH UI
# ============================================
st.markdown("<h1 style='color:white;'>🧬 Clinical Trial Finder</h1>", unsafe_allow_html=True)

# PATIENT DETAILS
st.markdown('<div class="section-title">PATIENT DETAILS</div>', unsafe_allow_html=True)
age = st.number_input("Age", min_value=1, max_value=120)
gender = st.radio("Gender", ["Male", "Female", "All"])
ecog = st.selectbox("ECOG Performance Status", [0, 1, 2, 3, 4], index=1)
st.caption("0 = Fully Active, 4 = Bedbound")

# DIAGNOSIS & HISTORY
st.markdown('<div class="section-title">DIAGNOSIS & HISTORY</div>', unsafe_allow_html=True)

ALLOWED_CONDITIONS = [
    "NSCLC", "Breast_Cancer", "Heart_Failure", "Chronic_Kidney_Disease",
    "Respiratory_Failure", "Liver_Failure", "Leukemia", "Prostate_Cancer",
    "Skin_Cancer", "Cervical_Cancer", "Bone_Cancer"
]

condition_input = st.text_input("Primary Diagnosis / Condition", placeholder="e.g. Lung Cancer, Skin Cancer")
condition_normalized = condition_input.strip().replace(" ", "_") if condition_input else ""

if condition_normalized and condition_normalized not in ALLOWED_CONDITIONS:
    st.error(f"Invalid condition: {condition_input}. Allowed: {', '.join(ALLOWED_CONDITIONS)}")
    conditions_payload = []
else:
    conditions_payload = [condition_normalized] if condition_normalized else []

biomarkers = st.multiselect(
    "Genomic Markers / Status",
    ["EGFR", "HER2", "ALK", "KRAS", "BRAF", "BCR-ABL", "FLT3", "CD19", "ER", "PR"]
)

history_input = st.text_area("History / Comorbidities (one per line)")
history_list = [line.strip() for line in history_input.split("\n") if line.strip()]

prior_lines = st.number_input("Prior Lines of Therapy", min_value=0, value=0)
days_since_last_treatment = st.number_input("Days Since Last Treatment", min_value=0, value=30)

# LAB VALUES
st.markdown('<div class="section-title">LAB VALUES</div>', unsafe_allow_html=True)

labs = {
    "Creatinine": st.number_input("Creatinine (mg/dL)", min_value=0.0, value=0.0),
    "GFR": st.number_input("GFR (mL/min)", min_value=0.0, value=0.0),
    "Bilirubin": st.number_input("Bilirubin (mg/dL)", min_value=0.0, value=0.0),
    "AST": st.number_input("AST (U/L)", min_value=0.0, value=0.0),
    "ALT": st.number_input("ALT (U/L)", min_value=0.0, value=0.0),
    "Platelet_Count": st.number_input("Platelet Count (10^9/L)", min_value=0.0, value=0.0),
    "Hemoglobin": st.number_input("Hemoglobin (g/dL)", min_value=0.0, value=0.0),
    "PSA": st.number_input("PSA (ng/mL)", min_value=0.0, value=0.0)
}
labs = {k: v for k, v in labs.items() if v > 0}

# PAYLOAD
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

# RUN RANKING
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

# SHOW RESULTS
st.markdown("<h2 style='color:white;margin-top:20px;margin-bottom:20px'>SEARCH RESULTS</h2>",
            unsafe_allow_html=True)

render_results(st.session_state.get("results", []))
