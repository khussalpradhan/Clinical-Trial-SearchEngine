import streamlit as st

def render_results(results):
    if not results:
        st.info("No results yet.")
        return

    for idx, trial in enumerate(results):
        title = trial.get("title", "Untitled Study")
        phase = trial.get("phase", "N/A")
        status = trial.get("overall_status", "N/A")
        brief_summary = trial.get("brief_summary", "No summary available.")

        # Card container
        with st.container():
            # Background using markdown (no div wraps the button)
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

            # Card content inside a sub-container
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

                # Button is inside the same container — visually INSIDE the card
                if st.button("View Details", key=f"view_{idx}"):
                    st.session_state.selected_trial = trial
                    st.session_state.page = "trial"
                    st.rerun()

                # Close the box
                st.markdown("</div>", unsafe_allow_html=True)
