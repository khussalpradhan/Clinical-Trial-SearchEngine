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

        st.markdown(f"""
        <div style="
            background-color:#0d0d0d;
            padding:18px;
            border-radius:14px;
            border:1px solid #222;
            margin-bottom:18px;
            transition:0.2s;
        ">
            <h3 style="margin:0; color:#00eaff; font-size:22px;">{title}</h3>
            <p style="margin:4px 0 10px 0; color:#ccc;">Phase {phase} • {status}</p>

            <a href="?page=trial&nct_id={nct}" style="
                background:#00eaff;
                padding:8px 14px;
                color:black;
                font-weight:600;
                border-radius:6px;
                text-decoration:none;
            ">View Details</a>
        </div>
        """, unsafe_allow_html=True)
