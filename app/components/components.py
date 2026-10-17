"""Reusable UI building blocks for RingSight.

Lean on Streamlit-native widgets (metrics, dataframes with ``help=``) and use
custom HTML only for small, themed elements (pills, chips, the why-flagged box).
All colour comes from :mod:`app.components.theme`.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.theme import icon, risk_band, tokens

# Screen order for the step indicator.
STEPS = [("upload", "Upload"), ("detect", "Detect"),
         ("investigate", "Investigate"), ("report", "Report")]

# Detector pattern key -> plain-language label (no jargon for the analyst).
PATTERN_LABEL = {
    "cycle": "Circular flow",
    "fan_in": "Structuring",
    "fan_out": "Layering",
    "shared_identifier": "Shared device/IP",
    "passthrough": "Rapid pass-through",
}


def pattern_label(patterns: list[str] | str) -> str:
    """Render one or more pattern keys as a readable label ('Circular flow +1')."""
    keys = ([p.strip() for p in patterns.split(",")] if isinstance(patterns, str)
            else list(patterns))
    keys = [k for k in keys if k]
    if not keys:
        return "—"
    head = PATTERN_LABEL.get(keys[0], keys[0])
    return f"{head} +{len(keys) - 1}" if len(keys) > 1 else head

# Display vocabulary for an object's one status (Razorpay-style state machine).
_STATUS_DISPLAY = {
    "New": ("Flagged", "medium"), "Flagged": ("Flagged", "medium"),
    "In Review": ("In review", "accent"), "In review": ("In review", "accent"),
    "Drafted": ("Drafted", "accent"),
    "Approved": ("Approved", "low"),
    "Rejected": ("Dismissed", "muted"), "Dismissed": ("Dismissed", "muted"),
}


# --- Navigation / state ------------------------------------------------------

def goto(step: str) -> None:
    """Switch the active screen and rerun."""
    st.session_state["rs_step"] = step
    st.rerun()


def current_step() -> str:
    return st.session_state.get("rs_step", "upload")


# --- Run log (Stripe event-log style) ----------------------------------------

def add_log(step: str, kind: str, detail: str) -> None:
    """Append one honest step to the run log. ``kind`` is 'Rule-based' or 'LLM'."""
    from datetime import datetime
    log = st.session_state.setdefault("rs_run_log", [])
    log.append({"time": datetime.now().strftime("%H:%M:%S"), "step": step,
                "type": kind, "detail": detail})
    st.session_state["rs_run_log"] = log[-40:]


def render_run_log() -> None:
    """A collapsed 'Run log' expander available on every screen."""
    log = st.session_state.get("rs_run_log", [])
    with st.expander(f"{icon('history')} Run log", expanded=False):
        if not log:
            st.caption("No runs yet in this session.")
            return
        df = pd.DataFrame(log)
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={"time": "Time", "step": "Step",
                                    "type": "Type", "detail": "Detail"})


# --- Small HTML atoms --------------------------------------------------------

def mono(text: str) -> str:
    return f"<span class='rs-mono'>{text}</span>"


def risk_pill(score: float) -> str:
    """Risk pill: coloured by band, always paired with a text label and the score."""
    band = risk_band(score)
    color = tokens()[f"risk_{band}"]
    label = {"high": "High", "medium": "Medium", "low": "Low"}[band]
    return (f"<span class='rs-pill' style='border-color:{color};color:{color}'>"
            f"{label}<span class='rs-num'>&nbsp;{score:.0f}</span></span>")


def status_pill(status: str) -> str:
    """Neutral status pill with a small coloured dot for the state."""
    label, tone = _STATUS_DISPLAY.get(status, (status, "muted"))
    t = tokens()
    dot = {"medium": t["risk_medium"], "accent": t["accent"],
           "low": t["risk_low"], "muted": t["text_muted"]}[tone]
    return (f"<span class='rs-pill rs-pill-muted'>"
            f"<span style='width:7px;height:7px;border-radius:50%;background:{dot};"
            f"display:inline-block'></span>{label}</span>")


def citation_chip(eid: str, bad: bool = False) -> str:
    cls = "rs-chip rs-chip-bad" if bad else "rs-chip"
    return f"<span class='{cls}'>{eid}</span>"


def entity_chip(label: str, value: str) -> str:
    return f"<span class='rs-chip-entity'>{label}: {mono(value)}</span>"


# --- Composite blocks --------------------------------------------------------

def why_flagged_box(sentence: str, measured: str) -> None:
    """The 'Why this was flagged' box — rule-based reason above the numbers."""
    st.markdown(
        f"<div class='rs-why'><div class='rs-tag'>Rule-based</div>"
        f"<div class='rs-sentence'>{sentence}</div>"
        f"<div class='rs-mono' style='color:var(--rs-muted);font-size:13px'>{measured}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def kpi_row(items: list[tuple[str, str, str]]) -> None:
    """Row of KPI cards. Each item is (label, value, help_tooltip)."""
    cols = st.columns(len(items))
    for col, (label, value, help_text) in zip(cols, items, strict=True):
        with col, st.container(border=True):
            st.metric(label, value, help=help_text)


def empty_state(icon_name: str, title: str, body: str) -> None:
    st.markdown(
        f"<div class='rs-card' style='text-align:center;color:var(--rs-muted)'>"
        f"<div class='rs-sentence' style='font-weight:600;color:var(--rs-text)'>{title}</div>"
        f"<div>{body}</div></div>",
        unsafe_allow_html=True,
    )
    st.caption("")  # spacing
    _ = icon_name
