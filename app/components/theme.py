"""Design tokens + theming for the RingSight UI (single source of colour).

Light and dark are first-class. Tokens are defined once here and injected as CSS
variables; the active theme follows Streamlit (``st.context.theme.type``) and is
mirrored into the pyvis graph so everything agrees. No hex values live outside
this module (CLAUDE.md-style single source for colour).
"""

from __future__ import annotations

import streamlit as st

# --- Token palettes (exact values from the design spec) ----------------------

LIGHT = {
    "bg": "#FFFFFF", "surface": "#F7F8FA", "border": "#E4E7EC",
    "text": "#101828", "text_muted": "#5B6474", "accent": "#2557D6",
    "risk_high": "#D92D20", "risk_medium": "#B54708", "risk_low": "#475467",
    "cite_bg": "#EEF3FF", "unsupported": "#FEF0C7",
}

DARK = {
    "bg": "#0B0D12", "surface": "#12151C", "border": "#232833",
    "text": "#E6E8EC", "text_muted": "#9AA3B2", "accent": "#6E9BFF",
    "risk_high": "#F97066", "risk_medium": "#FDB022", "risk_low": "#98A2B3",
    "cite_bg": "#1A2440", "unsupported": "#3D2E0A",
}


def active_mode() -> str:
    """Return the active theme type ('light' or 'dark'), following Streamlit."""
    try:
        t = getattr(st.context, "theme", None)
        if t is not None and getattr(t, "type", None) in ("light", "dark"):
            return t.type
    except Exception:
        pass
    return "light"


def tokens() -> dict:
    """The active token set."""
    return DARK if active_mode() == "dark" else LIGHT


def risk_band(score: float) -> str:
    """Map a 0-100 score to a band using the documented thresholds (>=70 / >=40)."""
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def risk_color(score: float) -> str:
    """Colour for a risk score (risk colours are only ever used for risk)."""
    return tokens()[f"risk_{risk_band(score)}"]


def icon(name: str) -> str:
    """Material Symbol reference for a Streamlit label (e.g. ``icon('hub')``)."""
    return f":material/{name}:"


def inject() -> None:
    """Inject fonts + CSS variables for the active theme and the component styles.

    One minimal block. Selectors that target Streamlit internals are commented.
    """
    t = tokens()
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap');
        :root {{
          --rs-bg: {t['bg']}; --rs-surface: {t['surface']}; --rs-border: {t['border']};
          --rs-text: {t['text']}; --rs-muted: {t['text_muted']}; --rs-accent: {t['accent']};
          --rs-high: {t['risk_high']}; --rs-medium: {t['risk_medium']}; --rs-low: {t['risk_low']};
          --rs-cite: {t['cite_bg']}; --rs-unsupported: {t['unsupported']};
        }}
        html, body, [class*="css"] {{ font-family: 'Inter', system-ui, sans-serif; }}
        /* Streamlit internals: hide footer + deploy button, keep the ⋮ menu so
           the viewer can switch Light/Dark (Settings -> Theme). Slim the header. */
        footer, [data-testid="stToolbarActions"] {{ visibility: hidden; height: 0; }}
        header[data-testid="stHeader"] {{ background: transparent; height: 2.2rem; }}
        .block-container {{ padding-top: 0.8rem; padding-bottom: 3rem; max-width: 1360px; }}

        .rs-mono {{ font-family: 'JetBrains Mono', ui-monospace, monospace;
                    font-variant-numeric: tabular-nums; }}
        .rs-num {{ font-variant-numeric: tabular-nums; }}

        /* Top bar */
        .rs-topbar {{ display:flex; align-items:center; gap:16px; padding:4px 0 12px;
                      border-bottom:1px solid var(--rs-border); margin-bottom:16px; }}
        .rs-wordmark {{ font-weight:600; font-size:20px; color:var(--rs-text); }}
        .rs-dataset {{ color:var(--rs-muted); font-size:13px; }}

        /* Pills */
        .rs-pill {{ display:inline-flex; align-items:center; gap:6px; padding:1px 8px;
                    border-radius:6px; font-size:12px; font-weight:600; line-height:18px;
                    border:1px solid var(--rs-border); }}
        .rs-pill-muted {{ color:var(--rs-muted); background:var(--rs-surface); }}

        /* Steps */
        .rs-steps {{ display:flex; gap:6px; align-items:center; margin-left:auto; }}
        .rs-step {{ font-size:13px; color:var(--rs-muted); }}
        .rs-step-active {{ color:var(--rs-text); font-weight:600; }}
        .rs-step-sep {{ color:var(--rs-border); }}

        /* KPI */
        .rs-kpi {{ background:var(--rs-bg); border:1px solid var(--rs-border);
                   border-radius:6px; padding:14px 16px; }}
        .rs-kpi .label {{ color:var(--rs-muted); font-size:13px; }}
        .rs-kpi .value {{ color:var(--rs-text); font-size:24px; font-weight:600;
                          margin-top:2px; font-variant-numeric:tabular-nums; }}

        /* Cards / boxes */
        .rs-card {{ background:var(--rs-bg); border:1px solid var(--rs-border);
                    border-radius:6px; padding:16px; }}
        .rs-why {{ background:var(--rs-surface); border:1px solid var(--rs-border);
                   border-left:3px solid var(--rs-accent); border-radius:6px; padding:12px 14px; }}
        .rs-tag {{ font-size:11px; font-weight:600; color:var(--rs-muted);
                   text-transform:uppercase; letter-spacing:.04em; }}

        /* Citation chip + unsupported sentence */
        .rs-chip {{ font-family:'JetBrains Mono', monospace; font-size:12px;
                    background:var(--rs-cite); color:var(--rs-accent); border-radius:6px;
                    padding:1px 6px; margin-left:4px; white-space:nowrap; }}
        .rs-chip-bad {{ background:var(--rs-unsupported); color:var(--rs-text); }}
        .rs-sentence {{ padding:5px 2px; color:var(--rs-text); line-height:1.55; }}
        .rs-unsupported {{ background:var(--rs-unsupported); border-radius:6px;
                           padding:6px 10px; margin:3px 0; }}

        .rs-chip-entity {{ display:inline-block; font-size:12px; background:var(--rs-surface);
                           border:1px solid var(--rs-border); border-radius:6px;
                           padding:1px 8px; margin:2px 4px 2px 0; color:var(--rs-text); }}
        </style>
        """,
        unsafe_allow_html=True,
    )
