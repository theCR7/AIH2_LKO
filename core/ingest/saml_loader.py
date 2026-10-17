"""SAML-D loader: a synthetic AML transaction dataset with typology labels.

Oztas et al., "Enhancing Anti-Money Laundering: Development of a Synthetic Transaction
Monitoring Dataset", IEEE ICEBE 2023 (CC BY-NC-SA 4.0, cite the paper). 9.5M transactions,
0.1039% laundering, 17 laundering typologies.

Pipeline: download (resumable; Kaggle serves the CSV zipped) -> stream the 1 GB file in two
passes -> keep every laundering row plus a seeded sample of normal rows -> remap accounts to
the canonical ``ACC_####`` ids -> persist as the single active dataset.

Design notes
- **One currency, labelled honestly.** Only ``UK pounds -> UK pounds`` rows are kept (88.5% of
  rows, 62.5% of the laundering) and stored as ``GBP``; the app prints every amount in the
  dataset's own currency (``core.utils.active_currency``), never a hard-coded USD.
- **Sample by label, not head-N** (REVIEW_NOTES). Normal rows are mostly neighbours of
  laundering accounts (graph context) plus seeded background noise. Sizes live in
  ``config/rules.yaml`` (``ingest.saml``).
- **Typology labels survive.** ``Laundering_type`` is stored in ``gt_pattern`` so Metrics can
  show recall per typology. There is no ring id, so ring-level metrics do not apply.
- **The sample is cached** (``data/saml/sample_<key>.csv``) so only the first load scans the file.

The Kaggle token comes from ``KAGGLE_API_TOKEN`` (``.env``) and is never logged. No streamlit.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from core.config import DATA_DIR, Rules, load_rules
from core.db import clear_data, session_scope
from core.ingest.kaggle import KaggleDownloadError, download_dataset_file
from core.models import Account, Transaction
from core.utils import utcnow

KAGGLE_SLUG = "berkanoztas/synthetic-transaction-monitoring-dataset-aml"
FILENAME = "SAML-D.csv"
DATASET_ID = "saml_d"
SAML_DIR = DATA_DIR / "saml"

TIME, DATE, SND, RCV, AMT = "Time", "Date", "Sender_account", "Receiver_account", "Amount"
PCUR, RCUR, SLOC, RLOC = ("Payment_currency", "Received_currency",
                          "Sender_bank_location", "Receiver_bank_location")
PTYPE, LAB, TYP = "Payment_type", "Is_laundering", "Laundering_type"
_USECOLS = [TIME, DATE, SND, RCV, AMT, PCUR, RCUR, SLOC, RLOC, PTYPE, LAB, TYP]
_DTYPES = {SND: "int64", RCV: "int64", LAB: "int64"}
_CHUNK_ROWS = 1_000_000
_BACKGROUND_OVERSAMPLE = 3.0      # draw extra background rows per chunk, then trim exactly
_ZIP_MAGIC = b"PK"

ProgressFn = Callable[[str], None]


class SamlLoaderError(Exception):
    """A problem the analyst can act on. Messages are safe to show (no secrets)."""


@dataclass
class SamlSample:
    """Result of sampling + remapping, ready to persist."""

    accounts: list[dict]
    txns: list[dict]
    stats: dict = field(default_factory=dict)


# --- Download -----------------------------------------------------------------

def local_path() -> Path:
    """Where the extracted CSV lives (git-ignored ``data/saml/``)."""
    return SAML_DIR / FILENAME


def is_downloaded() -> bool:
    return local_path().exists()


def _extract_member(archive: Path, member: str, dest_dir: Path) -> None:
    """Extract only the one expected member; refuse any other archive layout."""
    try:
        with zipfile.ZipFile(archive) as z:
            if member not in z.namelist() or "/" in member or ".." in member:
                raise SamlLoaderError("The downloaded archive does not contain "
                                      f"{member} as expected.")
            z.extract(member, dest_dir)
    except zipfile.BadZipFile:
        archive.unlink(missing_ok=True)
        raise SamlLoaderError("The downloaded file was damaged. Click Load SAML-D sample "
                              "again to re-download it.") from None


def download_saml_d(force: bool = False,
                    on_progress: Callable[[int], None] | None = None) -> Path:
    """Download SAML-D into ``data/saml/`` (about 200 MB zipped; skipped if already there)."""
    csv = local_path()
    if csv.exists() and not force:
        return csv
    archive = SAML_DIR / (FILENAME + ".zip")
    try:
        download_dataset_file(
            KAGGLE_SLUG, FILENAME, archive, on_progress=on_progress, force=force,
            manual_hint="place SAML-D.csv in data/saml/.",
            retry_hint="click Load SAML-D sample again to resume.")
    except KaggleDownloadError as exc:
        raise SamlLoaderError(str(exc)) from None

    if archive.read_bytes()[:2] == _ZIP_MAGIC:
        _extract_member(archive, FILENAME, SAML_DIR)
        archive.unlink(missing_ok=True)
    else:                                   # Kaggle served the raw CSV
        archive.replace(csv)
    return csv


# --- Row selection (pure over iterables of DataFrames; unit-tested offline) ---------

def _usable(chunk: pd.DataFrame, currency: str) -> pd.Series:
    """Single-currency, non-self, positive-amount rows."""
    return ((chunk[PCUR] == currency) & (chunk[RCUR] == currency)
            & (chunk[SND] != chunk[RCV]) & (chunk[AMT] > 0))


def scan_positives(chunks: Iterable[pd.DataFrame], currency: str) -> tuple[pd.DataFrame, dict]:
    """Pass 1: collect every usable laundering row and count the file."""
    parts: list[pd.DataFrame] = []
    stats = {"source_rows": 0, "usable_rows": 0, "laundering_total": 0, "laundering_usable": 0}
    for chunk in chunks:
        ok = _usable(chunk, currency)
        lab = chunk[LAB] == 1
        stats["source_rows"] += len(chunk)
        stats["usable_rows"] += int(ok.sum())
        stats["laundering_total"] += int(lab.sum())
        keep = chunk[ok & lab]
        stats["laundering_usable"] += len(keep)
        parts.append(keep)
    positives = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=_USECOLS)
    return positives, stats


def pick_normals(chunks: Iterable[pd.DataFrame], bad_accounts: set, currency: str, *,
                 normal_rows: int, budget: int, context_share: float,
                 seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pass 2: normal rows touching laundering accounts, plus a seeded background draw."""
    rng = np.random.RandomState(seed)
    frac = min(1.0, _BACKGROUND_OVERSAMPLE * budget * (1 - context_share) / max(normal_rows, 1))
    touch_parts: list[pd.DataFrame] = []
    background_parts: list[pd.DataFrame] = []
    for chunk in chunks:
        normal = chunk[_usable(chunk, currency) & (chunk[LAB] != 1)]
        touching = normal[SND].isin(bad_accounts) | normal[RCV].isin(bad_accounts)
        touch_parts.append(normal[touching])
        rest = normal[~touching]
        background_parts.append(rest[rng.rand(len(rest)) < frac])
    empty = pd.DataFrame(columns=_USECOLS)
    touch = pd.concat(touch_parts, ignore_index=True) if touch_parts else empty
    background = pd.concat(background_parts, ignore_index=True) if background_parts else empty
    return touch, background


def choose_rows(positives: pd.DataFrame, touch: pd.DataFrame, background: pd.DataFrame, *,
                max_total: int, context_share: float, seed: int) -> tuple[pd.DataFrame, dict]:
    """Trim the candidates to exactly the budget: all positives first (down-sampled only if
    they alone exceed it), then context rows, then background rows."""
    if len(positives) > max_total:
        positives = positives.sample(n=max_total, random_state=seed)
    budget = max(max_total - len(positives), 0)
    n_context = min(int(budget * context_share), len(touch))
    context = touch.sample(n=n_context, random_state=seed)
    n_background = min(budget - n_context, len(background))
    extra = background.sample(n=n_background, random_state=seed)
    chosen = pd.concat([positives, context, extra], ignore_index=True)
    return chosen, {"laundering_kept": len(positives), "context_kept": n_context,
                    "background_kept": n_background}


def remap(chosen: pd.DataFrame, currency_code: str) -> SamlSample:
    """Sort deterministically and rewrite ids to ``ACC_####`` / ``T######``."""
    df = chosen.copy()
    df["ts"] = pd.to_datetime(df[DATE].astype(str) + " " + df[TIME].astype(str))
    df = df.sort_values(["ts", SND, RCV, AMT], kind="mergesort").reset_index(drop=True)

    keys = sorted(set(df[SND]) | set(df[RCV]))
    acc_id = {k: f"ACC_{i:04d}" for i, k in enumerate(keys, start=1)}
    location: dict[int, str] = {}
    for key, loc in zip(df[SND], df[SLOC], strict=True):
        location.setdefault(key, str(loc))
    for key, loc in zip(df[RCV], df[RLOC], strict=True):
        location.setdefault(key, str(loc))

    now = utcnow()
    accounts = [{"account_id": acc_id[k], "name": acc_id[k], "bank": f"{location[k]} bank",
                 "country": location[k][:8], "account_type": "individual", "created_at": now}
                for k in keys]
    txns = []
    for i, row in enumerate(df.to_dict("records"), start=1):
        laundering = int(row[LAB]) == 1
        txns.append({
            "txn_id": f"T{i:06d}", "sender_id": acc_id[row[SND]], "receiver_id": acc_id[row[RCV]],
            "amount": round(float(row[AMT]), 2), "currency": currency_code,
            "ts": row["ts"].to_pydatetime(), "channel": str(row[PTYPE]), "ip": None,
            "device_id": None, "is_laundering": int(laundering),
            "gt_pattern": str(row[TYP]) if laundering else None, "gt_ring_id": None})
    kept_types = Counter(t["gt_pattern"] for t in txns if t["gt_pattern"])
    return SamlSample(accounts=accounts, txns=txns, stats={
        "transactions": len(txns), "accounts": len(accounts),
        "typologies_kept": dict(kept_types.most_common())})


# --- Persist + one-call entry point ---------------------------------------------

def persist_saml(sample: SamlSample, dataset_id: str = DATASET_ID) -> None:
    """Replace the active dataset with the sample (LLM cache preserved)."""
    clear_data(keep_llm_cache=True)
    with session_scope() as session:
        session.bulk_insert_mappings(Account, sample.accounts)
        session.bulk_insert_mappings(
            Transaction, [{**t, "dataset_id": dataset_id} for t in sample.txns])


def _read_chunks(path: Path) -> Iterable[pd.DataFrame]:
    return pd.read_csv(path, usecols=_USECOLS, dtype=_DTYPES, chunksize=_CHUNK_ROWS)


def _cache_files(path: Path, cfg) -> tuple[Path, Path]:
    key = "|".join(str(x) for x in (path.stat().st_size, cfg.max_transactions, cfg.context_share,
                                    cfg.seed, cfg.currency))
    stem = SAML_DIR / f"sample_{hashlib.md5(key.encode()).hexdigest()[:10]}"
    return stem.with_suffix(".csv"), stem.with_suffix(".json")


def load_saml_subset(path: Path | None = None, rules: Rules | None = None, persist: bool = True,
                     on_progress: ProgressFn | None = None) -> SamlSample:
    """Load, sample and (optionally) persist SAML-D. Downloads the file first if needed."""
    cfg = (rules or load_rules()).ingest.saml
    say = on_progress or (lambda _msg: None)
    csv = path or download_saml_d()
    sample_csv, sample_meta = _cache_files(csv, cfg)

    if sample_csv.exists() and sample_meta.exists():
        say("Reusing the sample saved from the last load")
        chosen = pd.read_csv(sample_csv, dtype=_DTYPES)
        stats = json.loads(sample_meta.read_text(encoding="utf-8"))
    else:
        try:
            say("Scanning the file for laundering rows (pass 1 of 2)")
            positives, stats = scan_positives(_read_chunks(csv), cfg.currency)
            budget = max(cfg.max_transactions - min(len(positives), cfg.max_transactions), 0)
            bad = set(positives[SND]) | set(positives[RCV])
            say("Sampling normal traffic around them (pass 2 of 2)")
            touch, background = pick_normals(
                _read_chunks(csv), bad, cfg.currency,
                normal_rows=stats["usable_rows"] - stats["laundering_usable"], budget=budget,
                context_share=cfg.context_share, seed=cfg.seed)
        except (ValueError, KeyError) as exc:
            raise SamlLoaderError(f"Unexpected SAML-D file format ({type(exc).__name__}). "
                                  "Expected the 12-column SAML-D.csv.") from None
        chosen, kept = choose_rows(positives, touch, background,
                                   max_total=cfg.max_transactions,
                                   context_share=cfg.context_share, seed=cfg.seed)
        stats.update(kept)
        SAML_DIR.mkdir(parents=True, exist_ok=True)
        chosen.to_csv(sample_csv, index=False)
        sample_meta.write_text(json.dumps(stats), encoding="utf-8")

    sample = remap(chosen, cfg.currency_code)
    sample.stats.update(stats)
    if persist:
        persist_saml(sample)
    return sample
