"""RingSight — Data (Screen 2): generate synthetic data or upload a CSV, then run detection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.components import data_access as da
from app.components.styles import render_sidebar, set_page
from app.components.ui import friendly_errors
from core.ingest.csv_loader import OPTIONAL_FIELDS, REQUIRED_FIELDS, load_dataframe
from core.ingest.generator import PlantedCounts, generate

set_page("Data")
render_sidebar("Data")
st.markdown("<h2 class='rs-title'>Data</h2>", unsafe_allow_html=True)

# Common header aliases to pre-select the right column in the mapping UI.
_ALIASES = {
    "sender": ["sender", "sender_id", "from", "src", "source", "originator"],
    "receiver": ["receiver", "receiver_id", "to", "dst", "dest", "beneficiary"],
    "amount": ["amount", "value", "amt"],
    "timestamp": ["timestamp", "ts", "time", "date", "datetime"],
    "currency": ["currency", "ccy"],
    "channel": ["channel", "type", "method"],
    "ip": ["ip", "ip_address"],
    "device_id": ["device_id", "device", "deviceid"],
}


def _guess(columns, field: str) -> int:
    """Return the index into ['— none —', *columns] that best matches a field."""
    lowered = {c.lower(): i for i, c in enumerate(columns)}
    for alias in _ALIASES.get(field, [field]):
        if alias in lowered:
            return lowered[alias] + 1  # +1 for the leading '— none —'
    return 0

tab_gen, tab_upload, tab_ibm = st.tabs(["Generate synthetic", "Upload CSV", "IBM AML sample"])


def _run_detection(dataset_id: str) -> None:
    from core.detection.runner import run_detection
    with friendly_errors("running detection"):
        with st.spinner("Running all detectors…"):
            summary = run_detection(dataset_id)
        da.bump_version()
        st.success(f"Detection complete: {summary.n_alerts} alerts → {summary.n_cases} cases "
                   f"in {summary.duration_ms} ms.")
        st.caption("Open the **Cases** page to review ranked cases.")


# --- Generate synthetic ------------------------------------------------------
with tab_gen:
    st.write("Generate a seeded synthetic dataset with planted, labelled patterns.")
    c1, c2, c3, c4 = st.columns(4)
    n_accounts = c1.number_input("Accounts", 50, 5000, 500, step=50)
    n_txns = c2.number_input("Transactions", 500, 50000, 5000, step=500)
    days = c3.number_input("Days", 7, 180, 30, step=1)
    seed = c4.number_input("Seed", 0, 9999, 42, step=1)

    st.caption("Planted patterns")
    p1, p2, p3, p4, p5 = st.columns(5)
    cycles = p1.number_input("Cycles", 0, 10, 3)
    smurf = p2.number_input("Fan-in", 0, 10, 2)
    fanout = p3.number_input("Fan-out", 0, 10, 1)
    shared = p4.number_input("Shared-ID", 0, 10, 1)
    passthru = p5.number_input("Pass-through", 0, 10, 1)

    if st.button("Generate", type="primary"):
        with friendly_errors("generating synthetic data"):
            with st.spinner("Generating…"):
                res = generate(
                    n_accounts=int(n_accounts), n_txns=int(n_txns), days=int(days),
                    seed=int(seed),
                    planted=PlantedCounts(cycles=int(cycles), fan_in=int(smurf),
                                          fan_out=int(fanout), shared_id=int(shared),
                                          passthrough=int(passthru)),
                )
            st.session_state["rs_dataset"] = res.dataset_id
            da.bump_version()
            st.success(f"Generated {res.n_txns:,} transactions across {res.n_accounts} "
                       f"accounts ({len(res.rings)} planted rings). "
                       f"Dataset `{res.dataset_id}`.")
            if res.csv_path:
                st.caption(f"CSV written to `{res.csv_path}`")

    if da.load_kpis(da.current_dataset(), da.refresh_token(da.current_dataset()))["n_txns"]:
        st.divider()
        if st.button("Run detection", key="run_gen"):
            _run_detection(da.current_dataset())


# --- Upload CSV --------------------------------------------------------------
with tab_upload:
    st.write("Upload a transactions CSV and map its columns.")
    uploaded = st.file_uploader("Drop a CSV", type=["csv"])
    if uploaded is not None:
        with friendly_errors("reading the CSV file", stop=True):
            df = pd.read_csv(uploaded)
        st.caption(f"{len(df):,} rows · columns: {', '.join(df.columns)}")
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)

        st.subheader("Column mapping")
        options = ["— none —", *df.columns]
        mapping: dict[str, str] = {}
        mcols = st.columns(len(REQUIRED_FIELDS))
        for col, field in zip(mcols, REQUIRED_FIELDS, strict=True):
            choice = col.selectbox(f"{field} *", options,
                                   index=_guess(df.columns, field), key=f"map_{field}")
            if choice != "— none —":
                mapping[field] = choice
        ocols = st.columns(len(OPTIONAL_FIELDS))
        for col, field in zip(ocols, OPTIONAL_FIELDS, strict=True):
            choice = col.selectbox(field, options,
                                   index=_guess(df.columns, field), key=f"map_{field}")
            if choice != "— none —":
                mapping[field] = choice

        if st.button("Validate & load", type="primary"):
            result = load_dataframe(df, mapping, dataset_id="upload")
            if not result.ok:
                st.error("Load failed:")
                for err in result.errors[:20]:
                    st.write(f"- {err}")
            else:
                st.session_state["rs_dataset"] = "upload"
                da.bump_version()
                st.success(f"Loaded {result.n_txns:,} transactions "
                           f"across {result.n_accounts} accounts.")
                if result.errors:
                    with st.expander(f"{len(result.errors)} skipped rows"):
                        for err in result.errors[:50]:
                            st.write(f"- {err}")
                if result.preview is not None:
                    st.dataframe(result.preview, use_container_width=True, hide_index=True)

    if da.current_dataset() == "upload" and da.load_kpis(
        "upload", da.refresh_token("upload"))["n_txns"]:
        st.divider()
        if st.button("Run detection", key="run_upload"):
            _run_detection("upload")


# --- IBM AML sample (stretch) ------------------------------------------------
with tab_ibm:
    st.info("IBM AML (HI-Small) subset loader is a stretch goal (P10b) — not enabled "
            "in this build. Sample by `is_laundering` rather than head-N when added.")
