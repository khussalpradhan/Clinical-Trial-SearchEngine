import streamlit as st
import sys
from pathlib import Path

project_root = Path(__file__).parents[3].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from api_clients.trial_api import get_trial_details


def _clip(text, n=300):
    return (text[:n] + "…") if text and len(text) > n else (text or "")


def render_results(results):
    if not results:
        return

    st.markdown("""
    <style>
    .card-box {
        background-color: #111;
        padding: 25px;
        border-radius: 15px;
        border: 1px solid #222;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        f"<p style='color:#aaa; font-size:13px;'>{len(results)} trial(s) found</p>",
        unsafe_allow_html=True,
    )

    for idx, trial in enumerate(results):
        title         = trial.get("title", "Untitled Study")
        phase         = trial.get("phase", "N/A")
        status        = trial.get("overall_status", "N/A")
        brief_summary = trial.get("brief_summary", "No summary available.")
        nct_id        = trial.get("nct_id", "")

        with st.container():
            st.markdown(
                f"""
                <div class="card-box">
                    <h3 style="color:white; margin-top:0;">{title}</h3>
                    <p style="color:#9ca3af; font-size:13px; margin:4px 0 0 0;">
                        Phase {phase} &nbsp;•&nbsp; {status}
                        {"&nbsp;•&nbsp;<code style='font-size:12px;color:#6366f1'>" + nct_id + "</code>" if nct_id else ""}
                    </p>
                    <p style="color:#bbb; font-size:14px; margin-top:12px; line-height:1.6;">
                        {_clip(brief_summary, 300)}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("View Details →", key=f"view_{idx}"):
                if nct_id:
                    with st.spinner(f"Fetching details for {nct_id}…"):
                        details = get_trial_details(nct_id)
                    if details:
                        st.session_state.selected_trial = details
                    else:
                        st.session_state.selected_trial = trial
                else:
                    st.session_state.selected_trial = trial

                st.session_state.page = "trial"
                st.rerun()