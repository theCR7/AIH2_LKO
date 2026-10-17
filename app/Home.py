"""RingSight — single-entry app shell (run: ``streamlit run app/Home.py``).

Owns the persistent top bar, the Upload -> Detect -> Investigate -> Report step
nav, the narrow sidebar, and routing to one screen. Screens live in app/screens
and expose ``render()``. State lives in ``st.session_state`` (prefix ``rs_``) and
survives reruns.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.components import components as c
from app.components import data_access as da
from app.components.theme import brand_html, icon, inject
from app.components.ui import friendly_errors
from app.screens import audit, detect, investigate, report, upload
from core.config import load_rules

st.set_page_config(page_title="RingSight", layout="wide")
inject()

# Ensure the DB + data/ exist on first load (fresh clone never hits "no such table").
with friendly_errors("preparing the database"):
    from core.db import init_db
    init_db()

dataset = da.current_dataset()
version = da.refresh_token(dataset)
with friendly_errors("loading dataset summary", stop=False):
    kpis = da.load_kpis(dataset, version)
has_data = kpis["n_txns"] > 0
case_id = st.session_state.get("rs_case_id")
has_draft = case_id is not None and f"rs_sar_{case_id}" in st.session_state

reachable = {"upload"}
if has_data:
    reachable.add("detect")
    reachable.add("audit")
if has_data and case_id:
    reachable.add("investigate")
if has_draft:
    reachable.add("report")

# A fresh page load resumes at the case queue when data is already loaded.
st.session_state.setdefault("rs_step", "detect" if has_data else "upload")
step = c.current_step()
if step not in reachable:
    step = "detect" if has_data else "upload"
    st.session_state["rs_step"] = step


# --- Top bar -----------------------------------------------------------------

def _top_bar() -> None:
    rows = f"{kpis['n_txns']:,} rows" if has_data else "no data loaded"
    st.markdown(
        f"<div class='rs-topbar'>{brand_html()}<span class='rs-spacer'></span>"
        f"<span class='rs-dataset rs-mono'>{dataset} · {rows}</span>"
        f"<span class='rs-pill rs-pill-muted'>Synthetic data</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _step_nav() -> None:
    """Tab-style stepper: completed steps get a check, the current step is the accent
    tab, steps that are not reachable yet are greyed out (styled in theme.py)."""
    order = [key for key, _ in c.STEPS]
    current_index = order.index(step) if step in order else -1
    with st.container(key="stepnav"):
        cols = st.columns(len(c.STEPS) + 1)
        for i, (col, (key, label)) in enumerate(zip(cols, c.STEPS, strict=False)):
            with col:
                is_current = key == step
                done = i < current_index and key in reachable
                if st.button(f"{icon('check')} {label}" if done else label,
                             key=f"nav_{key}",
                             type="primary" if is_current else "secondary",
                             disabled=is_current or key not in reachable,
                             use_container_width=True):
                    c.goto(key)
        with cols[-1]:
            on_metrics = step == "audit"
            if st.button(f"{icon('monitoring')} Metrics", key="nav_audit",
                         type="primary" if on_metrics else "secondary",
                         disabled=on_metrics or not has_data, use_container_width=True):
                c.goto("audit")


_top_bar()
_step_nav()


# --- Sidebar -----------------------------------------------------------------

with st.sidebar:
    st.markdown(f"**{icon('database')} Data source**")
    st.caption(f"Dataset: `{dataset}`")
    from core.agents.llm import get_llm_status
    _status = get_llm_status()
    st.caption(f"LLM: {_status.get('label', _status['mode'])}")

    with st.popover(f"{icon('info')} How detection works", use_container_width=True):
        st.markdown(
            "- **Circular flow:** funds loop through 3-6 accounts and return to the "
            "origin, keeping most of their value each hop.\n"
            "- **Structuring (fan-in):** many senders pay one account amounts kept "
            "below the reporting threshold, within a short window.\n"
            "- **Layering (fan-out):** one account disperses a large sum to many "
            "receivers quickly.\n"
            "- **Shared identifier:** separate accounts transact from the same device "
            "or IP.\n"
            "- **Rapid pass-through:** an account forwards most of an inflow within a day.")

    with st.expander(f"{icon('tune')} Advanced"):
        r = load_rules()
        st.caption("Thresholds are read from `config/rules.yaml` (edit there to change).")
        st.caption(f"Cycle length: {r.cycles.min_length}-{r.cycles.max_length} hops, "
                   f"within {r.cycles.max_window_hours}h, "
                   f"≥{r.cycles.min_value_retention:.0%} retained per hop "
                   f"(default 3-6 / 168h / 80%).")
        st.caption(f"Fan-in: ≥{r.fan_in.min_senders} senders, each "
                   f"< {r.fan_in.max_amount_each:,.0f}, within {r.fan_in.window_hours}h.")
        st.caption(f"Fan-out: ≥{r.fan_out.min_receivers} receivers, total "
                   f"≥ {r.fan_out.min_total:,.0f}, within {r.fan_out.window_hours}h.")
        st.caption(f"Shared identifier: ≥{r.shared_identifiers.min_accounts} accounts.")
        st.caption(f"Pass-through: ≥{r.passthrough.min_outflow_ratio:.0%} forwarded "
                   f"within {r.passthrough.window_hours}h.")

    st.divider()
    if st.button(f"{icon('restart_alt')} Reset session", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith("rs_"):
                del st.session_state[k]
        st.cache_data.clear()
        st.rerun()


# --- Route -------------------------------------------------------------------

_SCREENS = {"upload": upload, "detect": detect, "investigate": investigate,
            "report": report, "audit": audit}
with friendly_errors(f"loading the {step} screen"):
    _SCREENS[step].render()

c.render_run_log()
