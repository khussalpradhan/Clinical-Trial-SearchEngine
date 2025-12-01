import streamlit as st
import sys
from pathlib import Path

project_root = Path(__file__).parents[3].resolve()  # app/ui/ -> frontend/
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))
    
from api_clients.trial_api import get_trial_details

def render_results(results):
    if not results:
        return

    for idx, trial in enumerate(results):
        title = trial.get("title", "Untitled Study")
        phase = trial.get("phase", "N/A")
        status = trial.get("overall_status", "N/A")
        brief_summary = trial.get("brief_summary", "No summary available.")

        # Card container
        with st.container():
            # Background using markdown
            st.markdown(
                """
                <style>
                .card-box {
                    background-color: #111;
                    padding: 25px;
                    border-radius: 15px;
                    border: 1px solid #222;
                    margin-bottom: 20px;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            card = st.container()
            with card:
                st.markdown(
                    f"""
                    <div class="card-box">
                        <h3 style="color:white; margin-top:0;">{title}</h3>
                        <p style="color:white;">Phase {phase} • {status}</p>
                        <p style="color:#bbb; font-size:14px; margin-top:10px;">
                            {brief_summary[:240]}...
                        </p>
                    """,
                    unsafe_allow_html=True,
                )

                # Fetch fresh trial details on click
                if st.button("View Details", key=f"view_{idx}"):
                    nct_id = trial.get("nct_id")
                    if nct_id:
                        with st.spinner(f"Fetching trial details for {nct_id}…"):
                            details = get_trial_details(nct_id)
                            if details:
                                st.session_state.selected_trial = details
                                st.session_state.page = "trial"
                                st.rerun()
                            else:
                                st.error("Could not fetch trial details from backend.")
                    else:
                        st.error("Invalid NCT ID.")

                st.markdown("</div>", unsafe_allow_html=True)
