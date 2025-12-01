import streamlit as st

def render_search_bar():
    st.subheader("Search Terms")
    return st.text_input(
        "Optional Free-Text Query",
        placeholder="e.g. EGFR exon 19 deletion, ALK+, NSCLC",
    )
