import streamlit as st
import sys
from pathlib import Path

project_root = Path(__file__).parents[3].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from api_clients.trial_api import get_trial_details


def _val(v, fallback="N/A"):
    return v if v not in (None, "", [], {}) else fallback


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


def _clip(text, n=500):
    return (text[:n] + "…") if text and len(text) > n else (text or "")


def _extract(data: dict) -> dict:
    """Pull all display fields from a data dict (search hit or detail response)."""
    elig_mod = data.get("eligibility") or {}
    if not isinstance(elig_mod, dict):
        elig_mod = {}

    min_age = _val(data.get("minimum_age") or data.get("min_age") or elig_mod.get("minimumAge"))
    max_age = _val(data.get("maximum_age") or data.get("max_age") or elig_mod.get("maximumAge"))
    sex     = _val(data.get("sex") or data.get("gender") or elig_mod.get("sex"))
    brief   = _val(data.get("brief_summary") or data.get("description"), "")

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
        "min_age": min_age,
        "max_age": max_age,
        "sex":     sex,
        "brief":   brief,
        "inc":     inc_raw,
        "exc":     exc_raw,
        "loc":     location_str,
    }


def render_results(results):
    if not results:
        return

    st.markdown("""
    <style>
    .tm-card {
        background: #111;
        border: 1px solid #222;
        border-radius: 16px;
        padding: 24px 28px;
        margin-bottom: 24px;
    }
    .tm-title  { color:#fff; font-size:1.05rem; font-weight:700; margin:0 0 6px 0; }
    .tm-badges { color:#9ca3af; font-size:13px; margin-bottom:14px; }
    .tm-accent { color:#818cf8; font-family:monospace; }
    .tm-label  {
        color:#6366f1; font-size:11px; font-weight:700;
        text-transform:uppercase; letter-spacing:.08em; margin:14px 0 4px 0;
    }
    .tm-text { color:#cbd5e1; font-size:13.5px; line-height:1.65; margin:0; }
    .tm-hr   { border:none; border-top:1px solid #1e2330; margin:14px 0; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        f"<p style='color:#6b7280;font-size:13px;margin-bottom:18px;'>"
        f"{len(results)} trial(s) found</p>",
        unsafe_allow_html=True,
    )

    if "detail_cache" not in st.session_state:
        st.session_state.detail_cache = {}

    for idx, trial in enumerate(results):
        nct_id = trial.get("nct_id", "") or f"idx_{idx}"

        # ── Fetch details once per trial, silently ───────────────────────────
        if nct_id not in st.session_state.detail_cache:
            if trial.get("nct_id"):
                fetched = get_trial_details(trial["nct_id"])
                st.session_state.detail_cache[nct_id] = fetched if fetched else trial
            else:
                st.session_state.detail_cache[nct_id] = trial

        data = st.session_state.detail_cache[nct_id]
        f    = _extract(data)

        with st.container():
            st.markdown(f"""
            <div class="tm-card">

                <p class="tm-title">{f['title']}</p>
                <p class="tm-badges">
                    Phase {f['phase']} &nbsp;•&nbsp; {f['status']}
                    {"&nbsp;•&nbsp;<span class='tm-accent'>" + trial.get('nct_id','') + "</span>" if trial.get('nct_id') else ""}
                </p>
                <hr class="tm-hr">

                <p class="tm-label">Eligibility</p>
                <p class="tm-text">
                    Min Age: <b style="color:#e2e8f0">{f['min_age']}</b>
                    &nbsp;|&nbsp;
                    Max Age: <b style="color:#e2e8f0">{f['max_age']}</b>
                    &nbsp;|&nbsp;
                    Sex: <b style="color:#e2e8f0">{f['sex']}</b>
                </p>

                <p class="tm-label">Summary</p>
                <p class="tm-text">{_clip(f['brief'], 400)}</p>

                <p class="tm-label">Inclusion Criteria</p>
                <p class="tm-text" style="white-space:pre-wrap">{_clip(f['inc'], 600) or "N/A"}</p>

                <p class="tm-label">Exclusion Criteria</p>
                <p class="tm-text" style="white-space:pre-wrap">{_clip(f['exc'], 600) or "N/A"}</p>

                <p class="tm-label">Location(s)</p>
                <p class="tm-text">{f['loc']}</p>

            </div>
            """, unsafe_allow_html=True)