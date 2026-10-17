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


def _use_ibm() -> bool:
    """Download (if needed), sample and detect the IBM AML HI-Small data.

    Returns True when the dataset is loaded and detection ran. Kaggle/auth/network
    problems are shown as one calm message (no traceback); details go to the run log.
    """
    from core.detection.runner import run_detection
    from core.ingest import ibm_loader as ibm

    with st.status("Loading IBM AML sample", expanded=True) as status:
        try:
            if ibm.is_downloaded():
                status.write("Using the copy already downloaded to data/")
                path = ibm.local_path()
            else:
                status.write("Downloading HI-Small_Trans.csv from Kaggle (about 475 MB)")
                progress = st.empty()
                path = ibm.download_hi_small(
                    on_progress=lambda n: progress.caption(f"{n / 1e6:,.0f} MB downloaded"))
                progress.empty()
            status.write("Reading, keeping every laundering row, sampling the rest")
            sample = ibm.load_ibm_subset(path=path)
        except ibm.IbmLoaderError as exc:
            c.add_log("IBM AML load failed", "Rule-based", str(exc))
            status.update(label="Could not load the IBM sample", state="error")
            st.error(str(exc))
            return False
        s = sample.stats
        c.add_log("Loaded IBM AML", "Rule-based",
                  f"{s['transactions']:,} of {s['usable_rows']:,} usable transfers "
                  f"({s['laundering_kept']:,} labelled laundering), {s['accounts']:,} accounts")
        status.write(f"Loaded {s['transactions']:,} transfers across {s['accounts']:,} "
                     f"accounts; {s['laundering_kept']:,} are labelled laundering")
        status.write("Running detectors and ranking cases")
        st.session_state["rs_dataset"] = ibm.DATASET_ID
        summary = run_detection(ibm.DATASET_ID)
        c.add_log("Detection", "Rule-based",
                  f"{summary.n_alerts} alerts -> {summary.n_cases} cases "
                  f"in {summary.duration_ms} ms")
        status.update(label=f"Ready: {summary.n_cases} cases flagged", state="complete")
    da.bump_version()
    return True


def _use_saml() -> bool:
    """Download (if needed), sample and detect the SAML-D data; True when it is loaded."""
    from core.detection.runner import run_detection
    from core.ingest import saml_loader as saml

    with st.status("Loading SAML-D sample", expanded=True) as status:
        try:
            if saml.is_downloaded():
                status.write("Using the copy already downloaded to data/saml/")
                path = saml.local_path()
            else:
                status.write("Downloading SAML-D from Kaggle (about 200 MB)")
                progress = st.empty()
                path = saml.download_saml_d(
                    on_progress=lambda n: progress.caption(f"{n / 1e6:,.0f} MB downloaded"))
                progress.empty()
            sample = saml.load_saml_subset(path=path, on_progress=status.write)
        except saml.SamlLoaderError as exc:
            c.add_log("SAML-D load failed", "Rule-based", str(exc))
            status.update(label="Could not load the SAML-D sample", state="error")
            st.error(str(exc))
            return False
        s = sample.stats
        c.add_log("Loaded SAML-D", "Rule-based",
                  f"{s['transactions']:,} transfers ({s['laundering_kept']:,} labelled laundering "
                  f"of {s['laundering_total']:,} in the file), {s['accounts']:,} accounts")
        status.write(f"Loaded {s['transactions']:,} transfers across {s['accounts']:,} "
                     f"accounts; {s['laundering_kept']:,} are labelled laundering")
        status.write("Running detectors and ranking cases")
        st.session_state["rs_dataset"] = saml.DATASET_ID
        summary = run_detection(saml.DATASET_ID)
        c.add_log("Detection", "Rule-based",
                  f"{summary.n_alerts} alerts -> {summary.n_cases} cases "
                  f"in {summary.duration_ms} ms")
        status.update(label=f"Ready: {summary.n_cases} cases flagged", state="complete")
    da.bump_version()
    return True


def render() -> None:
    from core.ingest import ibm_loader as ibm
    from core.ingest import saml_loader as saml

    st.subheader("Choose a data source")
    st.caption("All data is synthetic. Pick one to start; detection runs automatically "
               "and takes you to the case queue.")

    # One primary action per view: the sample button yields to "Load and run detection"
    # once a CSV has been uploaded.
    has_upload = st.session_state.get("rs_csv_upload") is not None
    sample_col, ibm_col, saml_col = st.columns(3, gap="medium")

    with sample_col, st.container(border=True):
        st.markdown("<div class='rs-source-title'>Synthetic sample</div>",
                    unsafe_allow_html=True)
        st.caption("500 accounts and about 5,000 transfers, with laundering patterns "
                   "planted for the demo. Ready in seconds.")
        if st.button(f"{icon('dataset')} Use sample",
                     type="secondary" if has_upload else "primary",
                     use_container_width=True):
            with friendly_errors("preparing the sample dataset"):
                _use_sample()
            c.goto("detect")

    with ibm_col, st.container(border=True):
        st.markdown("<div class='rs-source-title'>IBM AML benchmark</div>",
                    unsafe_allow_html=True)
        st.caption("Real labelled transactions from Kaggle (HI-Small), sampled by "
                   "laundering label to about 30,000 transfers. "
                   + ("A local copy is ready." if ibm.is_downloaded()
                      else "The first load downloads 475 MB."))
        if st.button(f"{icon('cloud_download')} Load IBM sample",
                     use_container_width=True):
            loaded = False
            with friendly_errors("loading the IBM AML sample"):
                loaded = _use_ibm()
            if loaded:
                c.goto("detect")

    with saml_col, st.container(border=True):
        st.markdown("<div class='rs-source-title'>SAML-D benchmark</div>",
                    unsafe_allow_html=True)
        st.caption("Labelled by laundering type (17 typologies), sampled to about 40,000 "
                   "transfers in UK pounds. "
                   + ("A local copy is ready." if saml.is_downloaded()
                      else "The first load downloads about 200 MB."))
        if st.button(f"{icon('cloud_download')} Load SAML-D sample",
                     use_container_width=True):
            loaded = False
            with friendly_errors("loading the SAML-D sample"):
                loaded = _use_saml()
            if loaded:
                c.goto("detect")

    with st.container(border=True):
        st.markdown("<div class='rs-source-title'>Your own CSV</div>",
                    unsafe_allow_html=True)
        st.caption("Upload transactions (up to 200 MB), then map your columns. Larger files "
                   "such as the benchmarks above are sampled by the loaders instead.")
        uploaded = st.file_uploader("Transactions CSV", type=["csv"],
                                    label_visibility="collapsed", key="rs_csv_upload")

    with st.expander("Expected CSV columns"):
        st.dataframe(
            pd.DataFrame(_SCHEMA, columns=["column", "type", "example", "requirement"]),
            use_container_width=True, hide_index=True)

    if uploaded is None:
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
