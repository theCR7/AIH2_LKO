"""Design tokens + theming for the RingSight UI (single source of colour).

The app ships a white-first light theme. ``THEME`` is the only switch: it is a fixed
choice, NOT read from the viewer's OS or browser. (An earlier version followed
``st.context.theme``, so on a dark-mode machine the injected text colours went light
while ``.streamlit/config.toml`` kept the page white, which left near-white text on a
white page.) To ship dark, set ``THEME = "dark"`` and ``base = "dark"`` in
``.streamlit/config.toml`` together. No hex values live outside this module.
"""

from __future__ import annotations

import streamlit as st

THEME = "light"  # "light" | "dark" — a deliberate project choice, never auto-detected

# --- Token palettes ----------------------------------------------------------

LIGHT = {
    "bg": "#FFFFFF", "surface": "#F6F8FA", "surface_hover": "#EEF2F7",
    "border": "#E3E8EF", "border_strong": "#CBD5E1",
    "text": "#0F172A", "text_muted": "#5B6B80",
    "accent": "#1D4ED8", "accent_strong": "#1E40AF", "accent_soft": "#EFF4FF",
    "on_accent": "#FFFFFF",
    "risk_high": "#D92D20", "risk_medium": "#B54708", "risk_low": "#475467",
    "cite_bg": "#EEF3FF", "unsupported": "#FEF0C7",
    "series_1": "#2A78D6", "series_2": "#EB6834", "series_3": "#1BAF7A",  # chart series (not risk)
}

DARK = {
    "bg": "#0B0D12", "surface": "#12151C", "surface_hover": "#1A1F2A",
    "border": "#232833", "border_strong": "#3A4252",
    "text": "#E6E8EC", "text_muted": "#9AA3B2",
    "accent": "#6E9BFF", "accent_strong": "#8FB0FF", "accent_soft": "#1A2440",
    "on_accent": "#0B0D12",
    "risk_high": "#F97066", "risk_medium": "#FDB022", "risk_low": "#98A2B3",
    "cite_bg": "#1A2440", "unsupported": "#3D2E0A",
    "series_1": "#3987E5", "series_2": "#D95926", "series_3": "#199E70",
}


def active_mode() -> str:
    """The theme the app renders in ('light' or 'dark'). Fixed by ``THEME``."""
    return "dark" if THEME == "dark" else "light"


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


def brand_html(tagline: bool = True) -> str:
    """Logo mark (a ring with one node on it) + wordmark, pure CSS so it never depends on SVG."""
    sub = "<span class='rs-tagline'>Multi-agent AML triage</span>" if tagline else ""
    return ("<span class='rs-logo'></span>"
            f"<span class='rs-brand'><span class='rs-wordmark'>RingSight</span>{sub}</span>")


def inject() -> None:
    """Inject fonts, CSS variables and component styles for the active theme.

    One block. Selectors that target Streamlit internals use its stable
    ``data-testid`` / ``st-key-*`` hooks and are commented.
    """
    t = tokens()
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap');
        :root {{
          --rs-bg: {t['bg']}; --rs-surface: {t['surface']}; --rs-surface-hover: {t['surface_hover']};
          --rs-border: {t['border']}; --rs-border-strong: {t['border_strong']};
          --rs-text: {t['text']}; --rs-muted: {t['text_muted']};
          --rs-accent: {t['accent']}; --rs-accent-strong: {t['accent_strong']};
          --rs-accent-soft: {t['accent_soft']}; --rs-on-accent: {t['on_accent']};
          --rs-high: {t['risk_high']}; --rs-medium: {t['risk_medium']}; --rs-low: {t['risk_low']};
          --rs-cite: {t['cite_bg']}; --rs-unsupported: {t['unsupported']};
        }}
        html, body, .stApp, [class*="css"] {{ font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }}
        .stApp {{ background: var(--rs-bg); color: var(--rs-text); }}

        /* Streamlit internals: hide footer + deploy button; slim the header. */
        footer, [data-testid="stToolbarActions"] {{ visibility: hidden; height: 0; }}
        header[data-testid="stHeader"] {{ background: transparent; height: 2.2rem; }}
        .block-container {{ padding-top: 0.6rem; padding-bottom: 3rem; max-width: 1280px; }}

        .rs-mono {{ font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
        .rs-num {{ font-variant-numeric: tabular-nums; }}

        /* ---- Headings (st.subheader renders an h3) ---- */
        [data-testid="stHeading"] h3 {{ font-size: 1.25rem; font-weight: 600; letter-spacing: -0.01em;
                                        color: var(--rs-text); padding-top: .25rem; }}
        /* Streamlit dims captions with opacity .6, which drops the real contrast below AA. */
        [data-testid="stCaptionContainer"] {{ color: var(--rs-muted); opacity: 1; }}
        .stApp code {{ color: var(--rs-accent-strong); background: var(--rs-accent-soft);
                       border-radius: 5px; padding: 1px 5px; font-size: .86em; }}

        /* ---- Brand + top bar ---- */
        .rs-topbar {{ display:flex; align-items:center; gap:12px; padding:6px 0 14px; }}
        .rs-logo {{ position:relative; flex:none; width:24px; height:24px; border-radius:50%;
                    border:3px solid var(--rs-accent); }}
        .rs-logo::after {{ content:""; position:absolute; top:-6px; right:-4px; width:9px; height:9px;
                           border-radius:50%; background:var(--rs-accent); box-shadow:0 0 0 2px var(--rs-bg); }}
        .rs-brand {{ display:flex; flex-direction:column; line-height:1.15; }}
        .rs-wordmark {{ font-weight:600; font-size:19px; letter-spacing:-0.01em; color:var(--rs-text); }}
        .rs-tagline {{ font-size:11.5px; color:var(--rs-muted); }}
        .rs-spacer {{ flex:1; }}
        .rs-dataset {{ color:var(--rs-muted); font-size:12.5px; }}

        /* ---- Pills ---- */
        .rs-pill {{ display:inline-flex; align-items:center; gap:6px; padding:2px 10px; border-radius:999px;
                    font-size:12px; font-weight:600; line-height:18px; border:1px solid var(--rs-border);
                    background:var(--rs-bg); }}
        .rs-pill-muted {{ color:var(--rs-muted); background:var(--rs-surface); }}

        /* ---- Sidebar ---- */
        [data-testid="stSidebar"] {{ background: var(--rs-surface); border-right: 1px solid var(--rs-border); }}
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: .5rem; }}
        .rs-side-brand {{ display:flex; align-items:center; gap:12px; padding:6px 0 4px; }}

        /* ---- Buttons (Streamlit exposes the kind on data-testid) ---- */
        button[data-testid="stBaseButton-primary"] {{
            background: var(--rs-accent); border: 1px solid var(--rs-accent); color: var(--rs-on-accent);
            border-radius: 8px; font-weight: 600; }}
        button[data-testid="stBaseButton-primary"]:hover:not(:disabled) {{
            background: var(--rs-accent-strong); border-color: var(--rs-accent-strong); color: var(--rs-on-accent); }}
        button[data-testid="stBaseButton-secondary"], button[data-testid="stPopoverButton"] {{
            background: var(--rs-bg); border: 1px solid var(--rs-border-strong); color: var(--rs-text);
            border-radius: 8px; font-weight: 500; }}
        button[data-testid="stBaseButton-secondary"]:hover:not(:disabled), button[data-testid="stPopoverButton"]:hover {{
            border-color: var(--rs-accent); color: var(--rs-accent); background: var(--rs-accent-soft); }}

        /* ---- Step bar: buttons inside the keyed container behave as tabs ---- */
        .st-key-stepnav {{ border-bottom: 1px solid var(--rs-border); margin-bottom: 1.1rem; }}
        .st-key-stepnav button {{ border: none !important; border-bottom: 2px solid transparent !important;
            border-radius: 0 !important; background: transparent !important; color: var(--rs-muted) !important;
            font-weight: 500 !important; box-shadow: none !important; padding: .45rem .25rem !important; }}
        .st-key-stepnav button:hover:not(:disabled) {{ color: var(--rs-accent) !important;
            background: var(--rs-accent-soft) !important; }}
        .st-key-stepnav button:disabled {{ opacity: .42; }}
        .st-key-stepnav button[data-testid="stBaseButton-primary"] {{ color: var(--rs-accent) !important;
            border-bottom-color: var(--rs-accent) !important; font-weight: 600 !important; opacity: 1; }}

        /* ---- Cards: bordered containers, metrics ---- */
        [data-testid="stVerticalBlockBorderWrapper"] {{ border-color: var(--rs-border); border-radius: 12px; }}
        [data-testid="stMetricLabel"] p {{ color: var(--rs-muted); font-size: .8rem; font-weight: 500; }}
        [data-testid="stMetricValue"] {{ font-size: 1.7rem; font-weight: 600; letter-spacing: -0.02em;
                                         color: var(--rs-text); font-variant-numeric: tabular-nums; }}
        [data-testid="stMetricValue"] > div {{ overflow: visible; text-overflow: clip; white-space: normal; }}

        /* ---- Inputs, uploader, tables, expanders, alerts ---- */
        [data-testid="stFileUploaderDropzone"] {{ background: var(--rs-surface);
            border: 1.5px dashed var(--rs-border-strong); border-radius: 12px; }}
        [data-testid="stDataFrame"] {{ border: 1px solid var(--rs-border); border-radius: 10px; overflow: hidden; }}
        [data-testid="stExpander"] details {{ border: 1px solid var(--rs-border); border-radius: 12px;
                                              background: var(--rs-bg); }}
        [data-testid="stAlert"] {{ border-radius: 10px; }}

        /* ---- Content blocks ---- */
        .rs-card {{ background:var(--rs-bg); border:1px solid var(--rs-border); border-radius:12px; padding:16px; }}
        .rs-why {{ background:var(--rs-surface); border:1px solid var(--rs-border);
                   border-left:3px solid var(--rs-accent); border-radius:10px; padding:12px 14px; }}
        .rs-tag {{ font-size:11px; font-weight:600; color:var(--rs-accent); text-transform:uppercase; letter-spacing:.05em; }}
        .rs-source-title {{ font-weight:600; font-size:1rem; color:var(--rs-text); margin-bottom:2px; }}

        /* ---- Citations ---- */
        .rs-chip {{ font-family:'JetBrains Mono', monospace; font-size:12px; background:var(--rs-cite);
                    color:var(--rs-accent); border-radius:6px; padding:1px 6px; margin-left:4px; white-space:nowrap; }}
        .rs-chip-bad {{ background:var(--rs-unsupported); color:var(--rs-text); }}
        .rs-sentence {{ padding:5px 2px; color:var(--rs-text); line-height:1.6; }}
        .rs-unsupported {{ background:var(--rs-unsupported); border-radius:8px; padding:6px 10px; margin:3px 0; }}
        .rs-chip-entity {{ display:inline-block; font-size:12px; background:var(--rs-surface);
                           border:1px solid var(--rs-border); border-radius:6px; padding:1px 8px;
                           margin:2px 4px 2px 0; color:var(--rs-text); }}
        </style>
        """,
        unsafe_allow_html=True,
    )
