"""Design tokens and shared chrome for the RingSight UI (WIREFRAMES design system).

Centralises the colour tokens, global CSS and the sidebar so every page looks
consistent. Only this module should define colours; pages import from here.
"""

from __future__ import annotations

import streamlit as st

from core.agents.llm import get_llm_status

# Design tokens (WIREFRAMES "Design tokens" table).
TOKENS = {
    "primary": "#1E3A8A",   # navy — header, primary buttons
    "accent": "#0EA5E9",    # sky — links, highlights
    "risk_high": "#DC2626",
    "risk_medium": "#F59E0B",
    "risk_low": "#16A34A",
    "grounded": "#16A34A",
    "ungrounded_bg": "#FEE2E2",
    "ungrounded_fg": "#DC2626",
    "surface": "#F8FAFC",
}


def band_color(score: float) -> str:
    """Return the risk colour for a score using WIREFRAMES bands."""
    if score >= 70:
        return TOKENS["risk_high"]
    if score >= 40:
        return TOKENS["risk_medium"]
    return TOKENS["risk_low"]


def set_page(title: str) -> None:
    """Apply wide layout + global CSS. Call once at the top of every page."""
    st.set_page_config(page_title=f"RingSight · {title}", layout="wide",
                       page_icon="🔎")
    _inject_css()


def _inject_css() -> None:
    """Inject the shared stylesheet (fonts, surface background, KPI cards)."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        html, body, [class*="css"] {{ font-family: 'Inter', system-ui, sans-serif; }}
        .stApp {{ background: {TOKENS['surface']}; }}
        .rs-kpi {{
            background: #ffffff; border: 1px solid #E2E8F0; border-radius: 14px;
            padding: 16px 18px; box-shadow: 0 1px 2px rgba(15,23,42,0.04);
        }}
        .rs-kpi .label {{ color: #64748B; font-size: 0.80rem; font-weight: 600;
            text-transform: uppercase; letter-spacing: .04em; }}
        .rs-kpi .value {{ color: {TOKENS['primary']}; font-size: 1.7rem; font-weight: 700;
            line-height: 1.2; margin-top: 4px; }}
        .rs-badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px;
            color: #fff; font-weight: 700; font-size: 0.80rem; }}
        .rs-title {{ color: {TOKENS['primary']}; font-weight: 700; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str) -> str:
    """Return HTML for a KPI card (render with st.markdown(unsafe_allow_html=True))."""
    return f'<div class="rs-kpi"><div class="label">{label}</div><div class="value">{value}</div></div>'


def risk_badge(score: float) -> str:
    """Return an HTML pill coloured by risk band."""
    return f'<span class="rs-badge" style="background:{band_color(score)}">{score:.0f}</span>'


def llm_status_label() -> str:
    """Describe the LLM gateway state for the sidebar pill."""
    status = get_llm_status()
    if status["mode"] == "mock":
        return "Mock ✓"
    keys = []
    if status.get("primary_key"):
        keys.append("Gemini ✓")
    if status.get("fallback_key"):
        keys.append("Groq ✓")
    return " / ".join(keys) if keys else "Live (no key)"


def _run_demo_mode() -> None:
    """One-click reproducible demo: reset data (keep cache), generate, detect, pre-warm."""
    from core.demo import run_demo

    with st.spinner("Resetting data, generating seed 42, detecting rings and "
                    "pre-warming the SAR cache…"):
        result = run_demo(seed=42, prewarm_top_n=2)
    # Point the UI at the fresh dataset and invalidate cached reads.
    st.session_state["rs_dataset"] = result.dataset_id
    st.session_state["rs_data_version"] = st.session_state.get("rs_data_version", 0) + 1
    st.session_state["rs_demo_fingerprint"] = result.fingerprint
    st.cache_data.clear()
    st.success(
        f"Demo ready · {result.n_cases} cases · pre-warmed "
        f"{', '.join(result.prewarmed_draft_ids) or 'none'}."
    )
    st.caption(f"Determinism fingerprint `{result.fingerprint[:12]}…` · "
               f"cache-hit ratio {result.cache_hit_ratio:.0%} "
               "(0% in mock mode — mock has no cache by design).")


def render_sidebar(active: str = "") -> None:
    """Render the shared sidebar: logo, LLM pill, dataset name, demo + reset buttons.

    Also ensures the database and its ``data/`` folder exist on first load so a
    fresh clone never hits a "no such table" error (ITERATIONS P9).
    """
    try:
        from core.db import init_db
        init_db()
    except Exception:
        pass
    with st.sidebar:
        st.markdown(
            "<h1 class='rs-title' style='margin-bottom:0'>🔎 RingSight</h1>"
            "<div style='color:#64748B;font-size:0.8rem;margin-bottom:12px'>"
            "AML Fraud-Ring & SAR Copilot</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"LLM: {llm_status_label()}")
        dataset = st.session_state.get("rs_dataset", "demo_seed42")
        st.caption(f"Dataset: `{dataset}`")
        st.divider()
        if st.button("🎬 Demo mode", type="primary", use_container_width=True,
                     help="Reset data (keeping the LLM cache), generate the seed-42 "
                          "dataset, run detection and pre-warm the top-2 SAR drafts. "
                          "Reproducible on every run."):
            try:
                _run_demo_mode()
            except Exception as exc:
                st.error(f"⚠️ Demo mode could not complete: {type(exc).__name__}: {exc}")
            else:
                st.rerun()
        if st.button("↺ Reset view", use_container_width=True,
                     help="Clear the current selection and cached reads (keeps data)."):
            for key in list(st.session_state.keys()):
                if key.startswith("rs_"):
                    del st.session_state[key]
            st.cache_data.clear()
            st.rerun()
