import streamlit as st

def render_results(results):
    if not results:
        st.info("No results yet.")
        return

    for trial in results:
        nct = trial.get("nct_id", "N/A")
        title = trial.get("title", "Untitled Study")
        phase = trial.get("phase", "N/A")
        status = trial.get("overall_status", "N/A")
        brief_summary = trial.get("brief_summary", "No summary available.")

        st.markdown(f"""
        <div class="trial-card">
            <h3>{title}</h3>
            <p>Phase {phase} • {status}</p>
            <p style="font-size:14px; color:#ccc; margin-top:4px;">{brief_summary[:150]}...</p>
            <a href="?page=trial&nct_id={nct}" style="
                display:inline-block;
                background-color:#222;
                padding:8px 14px;
                color:white;
                font-weight:600;
                border-radius:6px;
                text-decoration:none;
                margin-top:5px;
                font-size:14px;
            ">View Details</a>
        </div>
        """, unsafe_allow_html=True)
