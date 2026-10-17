"""Upload screen: load the sample dataset or a CSV, then run detection."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components import components as c
from app.components import data_access as da
from app.components.theme import icon
from app.components.ui import friendly_errors
from core.ingest.csv_loader import OPTIONAL_FIELDS, REQUIRED_FIELDS, load_dataframe

_ALIASES = {
    "sender": ["sender", "sender_id", "from", "src", "source", "originator"],
    "receiver": ["receiver", "receiver_id", "to", "dst", "dest", "beneficiary"],
    "amount": ["amount", "value", "amt"],
    "timestamp": ["timestamp", "ts", "time", "date", "datetime"],
    "currency": ["currency", "ccy"], "channel": ["channel", "type", "method"],
    "ip": ["ip", "ip_address"], "device_id": ["device_id", "device", "deviceid"],
}

_SCHEMA = [
    ("sender", "account id", "ACC_0018", "required"),
    ("receiver", "account id", "ACC_0033", "required"),
    ("amount", "number", "48200.00", "required"),
    ("timestamp", "datetime", "2026-09-03 10:14", "required"),
    ("currency", "text", "USD", "optional"),
    ("channel", "text", "transfer", "optional"),
    ("ip", "text", "10.0.0.5", "optional"),
    ("device_id", "text", "DEV_009", "optional"),
]


def _guess(columns, field: str) -> int:
    lowered = {col.lower(): i for i, col in enumerate(columns)}
    for alias in _ALIASES.get(field, [field]):
        if alias in lowered:
            return lowered[alias] + 1
    return 0


def _use_sample() -> None:
    from core.detection.runner import run_detection
    from core.ingest.generator import generate
    with st.status("Preparing sample case queue", expanded=True) as status:
        status.write("Generating synthetic dataset (seed 42)")
        res = generate(seed=42, persist=True, write_csv=True)
        c.add_log("Generated data", "Rule-based",
                  f"{res.n_txns:,} transfers, {res.n_accounts} accounts, "
                  f"{len(res.rings)} planted rings")
        status.write("Running detectors and ranking cases")
        summary = run_detection("demo_seed42")
        c.add_log("Detection", "Rule-based",
                  f"{summary.n_alerts} alerts -> {summary.n_cases} cases "
                  f"in {summary.duration_ms} ms")
        status.update(label=f"Ready: {summary.n_cases} cases flagged", state="complete")
    st.session_state["rs_dataset"] = "demo_seed42"
    da.bump_version()


def render() -> None:
    st.subheader("Upload transactions")
    st.caption("Load a transactions CSV, or use the built-in synthetic sample.")

    with st.container(border=True):
        uploaded = st.file_uploader("Transactions CSV", type=["csv"],
                                    label_visibility="collapsed")
        st.caption("Expected columns:")
        st.dataframe(
            pd.DataFrame(_SCHEMA, columns=["column", "type", "example", "requirement"]),
            use_container_width=True, hide_index=True)

    if uploaded is None:
        st.caption("No file? Use the synthetic sample: 500 accounts, ~5,000 transfers, "
                   "with known laundering patterns planted for the demo.")
        if st.button(f"{icon('dataset')} Use sample dataset", type="primary"):
            with friendly_errors("preparing the sample dataset"):
                _use_sample()
            c.goto("detect")
        return

    # --- Uploaded file: map columns, validate, load --------------------------
    with friendly_errors("reading the CSV", stop=True):
        df = pd.read_csv(uploaded)
    st.caption(f"{len(df):,} rows · columns: {', '.join(df.columns)}")

    with st.container(border=True):
        st.markdown("**Map your columns**")
        options = ["(none)", *df.columns]
        mapping: dict[str, str] = {}
        cols = st.columns(4)
        for i, field in enumerate(REQUIRED_FIELDS):
            with cols[i % 4]:
                pick = st.selectbox(f"{field} *", options, index=_guess(df.columns, field),
                                    key=f"map_{field}")
                if pick != "(none)":
                    mapping[field] = pick
        cols2 = st.columns(4)
        for i, field in enumerate(OPTIONAL_FIELDS):
            with cols2[i % 4]:
                pick = st.selectbox(field, options, index=_guess(df.columns, field),
                                    key=f"map_{field}")
                if pick != "(none)":
                    mapping[field] = pick

    if st.button(f"{icon('play_arrow')} Load and run detection", type="primary"):
        with friendly_errors("loading and detecting"):
            result = load_dataframe(df, mapping, dataset_id="upload")
            if not result.ok:
                for err in result.errors[:20]:
                    st.error(err)
                return
            st.session_state["rs_dataset"] = "upload"
            da.bump_version()
            c.add_log("Loaded CSV", "Rule-based",
                      f"{result.n_txns:,} rows, {result.n_accounts} accounts, "
                      f"{len(result.errors)} skipped")
            from core.detection.runner import run_detection
            summary = run_detection("upload")
            c.add_log("Detection", "Rule-based",
                      f"{summary.n_alerts} alerts -> {summary.n_cases} cases")
        c.goto("detect")
