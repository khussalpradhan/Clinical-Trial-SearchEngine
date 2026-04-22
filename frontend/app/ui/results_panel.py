import streamlit as st
import sys
from pathlib import Path

project_root = Path(__file__).parents[3].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from api_clients.trial_api import get_trial_details


def _val(v, fallback="N/A"):
    return v if v not in (None, "", [], {}) else fallback


def _clip(text, n=400):
    return (text[:n] + "…") if text and len(text) > n else (text or "")


def _parse_eligibility(raw: str):
    """Split a flat eligibility string into (inclusion, exclusion)."""
    if not raw:
        return "", ""
    raw_lower = raw.lower()
    inc_idx = raw_lower.find("inclusion criteria")
    exc_idx = raw_lower.find("exclusion criteria")
    if inc_idx == -1 and exc_idx == -1:
        return raw.strip(), ""
    if inc_idx != -1 and exc_idx != -1:
        return raw[inc_idx:exc_idx].strip(), raw[exc_idx:].strip()
    if inc_idx != -1:
        return raw[inc_idx:].strip(), ""
    return "", raw[exc_idx:].strip()


def _extract_fields(data: dict) -> dict:
    """Pull the 9 display fields from a data dict."""
    elig_mod = data.get("eligibility") or {}
    if not isinstance(elig_mod, dict):
        elig_mod = {}

    inc_raw = data.get("inclusion_criteria") or data.get("inclusion") or ""
    exc_raw = data.get("exclusion_criteria") or data.get("exclusion") or ""
    if not inc_raw and not exc_raw:
        raw_block = data.get("eligibility_criteria") or elig_mod.get("eligibilityCriteria") or ""
        inc_raw, exc_raw = _parse_eligibility(raw_block)

    locs_raw = data.get("locations") or data.get("location") or []
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
        location_str = "<br>".join(loc_parts) if loc_parts else "N/A"
    else:
        location_str = str(locs_raw) if locs_raw else "N/A"

    return {
        "title":   _val(data.get("official_title") or data.get("title")),
        "phase":   _val(data.get("phase")),
        "status":  _val(data.get("overall_status")),
        "min_age": _val(data.get("minimum_age") or data.get("min_age") or elig_mod.get("minimumAge")),
        "max_age": _val(data.get("maximum_age") or data.get("max_age") or elig_mod.get("maximumAge")),
        "sex":     _val(data.get("sex") or data.get("gender") or elig_mod.get("sex")),
        "brief":   _val(data.get("brief_summary") or data.get("description"), ""),
        "inc":     inc_raw,
        "exc":     exc_raw,
        "loc":     location_str,
    }


# ─────────────────────────────────────────────
# Detail view
# ─────────────────────────────────────────────

def _render_detail(data: dict, nct_id: str):
    """Render the full detail card for a single trial."""
    f = _extract_fields(data)

    st.markdown("""
    <style>
    .detail-card {
        background: #111;
        border: 1px solid #2a2a3a;
        border-radius: 18px;
        padding: 32px 36px;
        margin-top: 8px;
    }
    .d-title  { color:#fff; font-size:1.2rem; font-weight:700; margin:0 0 8px 0; line-height:1.4; }
    .d-badges { color:#9ca3af; font-size:13px; margin-bottom:0; }
    .d-accent { color:#818cf8; font-family:monospace; }
    .d-label  {
        color:#6366f1; font-size:11px; font-weight:700;
        text-transform:uppercase; letter-spacing:.08em; margin:20px 0 5px 0;
    }
    .d-text   { color:#cbd5e1; font-size:14px; line-height:1.7; margin:0; }
    .d-hr     { border:none; border-top:1px solid #1e2330; margin:18px 0; }
    </style>
    """, unsafe_allow_html=True)

    nct_badge = f"&nbsp;•&nbsp;<span class='d-accent'>{nct_id}</span>" if nct_id else ""

    st.markdown(f"""
    <div class="detail-card">
        <p class="d-title">{f['title']}</p>
        <p class="d-badges">
            Phase {f['phase']} &nbsp;•&nbsp; {f['status']}{nct_badge}
        </p>
        <hr class="d-hr">

        <p class="d-label">Eligibility</p>
        <p class="d-text">
            Min Age: <b style="color:#e2e8f0">{f['min_age']}</b>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Max Age: <b style="color:#e2e8f0">{f['max_age']}</b>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Sex: <b style="color:#e2e8f0">{f['sex']}</b>
        </p>

        <p class="d-label">Summary</p>
        <p class="d-text">{f['brief']}</p>

        <p class="d-label">Inclusion Criteria</p>
        <p class="d-text" style="white-space:pre-wrap">{f['inc'] or "N/A"}</p>

        <p class="d-label">Exclusion Criteria</p>
        <p class="d-text" style="white-space:pre-wrap">{f['exc'] or "N/A"}</p>

        <p class="d-label">Location(s)</p>
        <p class="d-text">{f['loc']}</p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("✕ Close", key=f"close_{nct_id}"):
        st.session_state.pop("open_detail", None)
        st.rerun()


# ─────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────

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

    if "open_detail" not in st.session_state:
        st.session_state.open_detail = None
    if "detail_cache" not in st.session_state:
        st.session_state.detail_cache = {}

    for idx, trial in enumerate(results):
        title         = trial.get("title", "Untitled Study")
        phase         = trial.get("phase", "N/A")
        status        = trial.get("overall_status", "N/A")
        brief_summary = trial.get("brief_summary", "No summary available.")
        nct_id        = trial.get("nct_id", "")
        card_key      = nct_id or f"idx_{idx}"

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
                if st.session_state.open_detail == card_key:
                    # clicking again closes it
                    st.session_state.open_detail = None
                else:
                    st.session_state.open_detail = card_key
                    # fetch + cache if not already done
                    if card_key not in st.session_state.detail_cache:
                        if nct_id:
                            with st.spinner(f"Fetching details for {nct_id}…"):
                                fetched = get_trial_details(nct_id)
                            st.session_state.detail_cache[card_key] = fetched if fetched else trial
                        else:
                            st.session_state.detail_cache[card_key] = trial
                st.rerun()

            # Render detail panel directly below this card
            if st.session_state.open_detail == card_key:
                detail_data = st.session_state.detail_cache.get(card_key, trial)
                _render_detail(detail_data, nct_id)