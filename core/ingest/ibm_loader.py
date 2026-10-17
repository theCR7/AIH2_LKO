"""IBM AML (HI-Small) loader — real labelled data from Kaggle (PRD F1.4, ITERATIONS P10b).

Pipeline: download ``HI-Small_Trans.csv`` (cached in ``data/``) -> clean -> sample by
``Is Laundering`` -> remap account ids to the canonical ``ACC_####`` format -> persist
as the single active dataset.

Design notes
- **Sample by label, not head-N** (REVIEW_NOTES): every laundering row is kept, then a
  seeded sample of normal rows — mostly neighbours of laundering accounts, so the graph
  has realistic context, plus background noise. Sizes come from ``rules.yaml``.
- **One currency.** The source mixes currencies; amounts are only comparable within one,
  so only ``ingest.ibm.currency`` (default US Dollar) rows are kept and labelled USD.
- **Canonical ids.** Account ids are unique only per bank, so the key is
  ``(bank, account)``; keys are sorted then numbered ``ACC_0001…`` so detection, scoring
  and the SAR validator treat every dataset uniformly. Transactions get ``T000001…``
  after a deterministic sort (CLAUDE.md rule #11).
- **Labels.** ``is_laundering`` is kept; there is no per-pattern ring label, so only
  transaction-level metrics apply (``core.metrics.txn_level_metrics``).

Credentials: the Kaggle token is read from the ``KAGGLE_API_TOKEN`` environment variable
(``.env``) and is never logged or placed in an error message. No streamlit here.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from core.config import DATA_DIR, Rules, load_rules
from core.db import clear_data, session_scope
from core.models import Account, Transaction
from core.utils import utcnow

KAGGLE_SLUG = "ealtman2019/ibm-transactions-for-anti-money-laundering-aml"
FILENAME = "HI-Small_Trans.csv"
DATASET_ID = "ibm_hismall"

# The file has two columns both named "Account"; we name all 11 columns explicitly.
_COLUMNS = ["timestamp", "from_bank", "from_account", "to_bank", "to_account",
            "amount_received", "receiving_currency", "amount_paid", "payment_currency",
            "payment_format", "is_laundering"]
_CHUNK_ROWS = 500_000
_DOWNLOAD_BLOCK = 1 << 20
_DOWNLOAD_TIMEOUT = 60      # seconds per socket read; a stall triggers a resume
_DOWNLOAD_ATTEMPTS = 8      # resumable attempts before asking the analyst to retry


class IbmLoaderError(Exception):
    """A problem the analyst can act on. Messages are safe to show (no secrets)."""


@dataclass
class IbmSample:
    """Result of sampling + remapping, ready to persist."""

    accounts: list[dict]
    txns: list[dict]
    stats: dict = field(default_factory=dict)


# --- Download ----------------------------------------------------------------

def local_path() -> Path:
    """Where the downloaded CSV is cached (git-ignored ``data/``)."""
    return DATA_DIR / FILENAME


def is_downloaded() -> bool:
    return local_path().exists()


def download_hi_small(force: bool = False,
                      on_progress: Callable[[int], None] | None = None) -> Path:
    """Download HI-Small from Kaggle into ``data/`` (skipped if already cached).

    Uses the Kaggle REST API with the ``KAGGLE_API_TOKEN`` bearer token, so no extra
    client library or username/key pair is needed. Raises :class:`IbmLoaderError`
    with a calm, secret-free message on any failure.
    """
    dest = local_path()
    if dest.exists() and not force:
        return dest

    token = os.getenv("KAGGLE_API_TOKEN", "").strip()
    if not token:
        raise IbmLoaderError("No Kaggle token configured. Add KAGGLE_API_TOKEN to .env, "
                             "or place HI-Small_Trans.csv in the data/ folder.")

    url = f"https://www.kaggle.com/api/v1/datasets/download/{KAGGLE_SLUG}/{FILENAME}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".part")
    if force:
        partial.unlink(missing_ok=True)

    last_error = "the connection stalled"
    for _attempt in range(_DOWNLOAD_ATTEMPTS):
        have = partial.stat().st_size if partial.exists() else 0
        headers = {"Authorization": f"Bearer {token}"}
        if have:
            headers["Range"] = f"bytes={have}-"   # resume where the last attempt stopped
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=_DOWNLOAD_TIMEOUT) as resp:
                resumed = have > 0 and resp.status == 206
                if not resumed:
                    have = 0
                expected = have + int(resp.headers.get("Content-Length") or 0)
                with open(partial, "ab" if resumed else "wb") as out:
                    total = have
                    while chunk := resp.read(_DOWNLOAD_BLOCK):
                        out.write(chunk)
                        total += len(chunk)
                        if on_progress:
                            on_progress(total)
            if expected and partial.stat().st_size != expected:
                last_error = "the download ended early"
                continue                        # truncated: resume from what we have
            partial.replace(dest)
            return dest
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and have:        # range past EOF: the file is already complete
                partial.replace(dest)
                return dest
            partial.unlink(missing_ok=True)
            if exc.code in (401, 403):
                raise IbmLoaderError("Kaggle rejected the token (HTTP "
                                     f"{exc.code}). Check KAGGLE_API_TOKEN in .env.") from None
            raise IbmLoaderError(
                f"Kaggle returned HTTP {exc.code} for the dataset file.") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}"   # keep the partial file and resume

    raise IbmLoaderError(f"The Kaggle download did not finish ({last_error}). Your progress "
                         "is kept: click Load IBM AML sample again to resume.")


# --- Transform (pure; unit-tested offline) ------------------------------------

def clean_ibm(df: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Keep single-currency, non-self, positive-amount rows and add account keys.

    ``df`` must use the standardised column names in ``_COLUMNS``. Adds ``from_key`` /
    ``to_key`` (``"<bank>:<account>"``) because ids are only unique within a bank.
    """
    keep = (df["payment_currency"] == currency) & (df["receiving_currency"] == currency)
    out = df.loc[keep].copy()
    out["from_key"] = out["from_bank"].astype(str) + ":" + out["from_account"].astype(str)
    out["to_key"] = out["to_bank"].astype(str) + ":" + out["to_account"].astype(str)
    out = out[(out["from_key"] != out["to_key"]) & (out["amount_paid"] > 0)]
    return out


def sample_ibm(df: pd.DataFrame, *, max_transactions: int, context_share: float,
               seed: int, source_rows: int | None = None) -> IbmSample:
    """Sample cleaned rows by label and remap to canonical ids.

    Keeps all laundering rows (down-sampled only if they alone exceed the budget), then
    fills the rest with normal rows: ``context_share`` of it from neighbours of
    laundering accounts, the remainder as seeded background. Deterministic for ``seed``.
    """
    laundering = df[df["is_laundering"] == 1]
    normal = df[df["is_laundering"] != 1]
    if len(laundering) > max_transactions:
        laundering = laundering.sample(n=max_transactions, random_state=seed)

    budget = max(max_transactions - len(laundering), 0)
    bad_accounts = set(laundering["from_key"]) | set(laundering["to_key"])
    touches = normal["from_key"].isin(bad_accounts) | normal["to_key"].isin(bad_accounts)
    context_pool, background_pool = normal[touches], normal[~touches]

    n_context = min(int(budget * context_share), len(context_pool))
    context = context_pool.sample(n=n_context, random_state=seed)
    n_background = min(budget - n_context, len(background_pool))
    background = background_pool.sample(n=n_background, random_state=seed)

    chosen = pd.concat([laundering, context, background], ignore_index=True)
    chosen["ts"] = pd.to_datetime(chosen["timestamp"], format="%Y/%m/%d %H:%M")
    chosen = chosen.sort_values(["ts", "from_key", "to_key", "amount_paid"],
                                kind="mergesort").reset_index(drop=True)

    keys = sorted(set(chosen["from_key"]) | set(chosen["to_key"]))
    acc_id = {k: f"ACC_{i:04d}" for i, k in enumerate(keys, start=1)}
    bank_of: dict[str, str] = {}
    for bank, key in zip(chosen["from_bank"], chosen["from_key"], strict=True):
        bank_of.setdefault(key, f"Bank {bank}")
    for bank, key in zip(chosen["to_bank"], chosen["to_key"], strict=True):
        bank_of.setdefault(key, f"Bank {bank}")

    now = utcnow()
    accounts = [{"account_id": acc_id[k], "name": acc_id[k], "bank": bank_of[k],
                 "country": "NA", "account_type": "individual", "created_at": now}
                for k in keys]
    txns = [
        {"txn_id": f"T{i:06d}", "sender_id": acc_id[s], "receiver_id": acc_id[r],
         "amount": round(float(a), 2), "currency": "USD", "ts": t.to_pydatetime(),
         "channel": str(fmt), "ip": None, "device_id": None,
         "is_laundering": int(lab), "gt_pattern": None, "gt_ring_id": None}
        for i, (s, r, a, t, fmt, lab) in enumerate(
            zip(chosen["from_key"], chosen["to_key"], chosen["amount_paid"], chosen["ts"],
                chosen["payment_format"], chosen["is_laundering"], strict=True), start=1)
    ]

    stats = {
        "source_rows": source_rows,
        "usable_rows": len(df),
        "laundering_in_pool": int((df["is_laundering"] == 1).sum()),
        "laundering_kept": len(laundering),
        "context_kept": int(n_context),
        "background_kept": int(n_background),
        "transactions": len(txns),
        "accounts": len(accounts),
    }
    return IbmSample(accounts=accounts, txns=txns, stats=stats)


def read_hi_small(path: Path, currency: str) -> tuple[pd.DataFrame, int]:
    """Stream the large CSV in chunks, cleaning each; return (cleaned rows, source rows)."""
    parts: list[pd.DataFrame] = []
    source_rows = 0
    reader = pd.read_csv(path, header=0, names=_COLUMNS, usecols=range(len(_COLUMNS)),
                         dtype={"from_bank": str, "from_account": str, "to_bank": str,
                                "to_account": str, "timestamp": str,
                                "receiving_currency": str, "payment_currency": str,
                                "payment_format": str},
                         chunksize=_CHUNK_ROWS)
    for chunk in reader:
        source_rows += len(chunk)
        parts.append(clean_ibm(chunk, currency))
    if not parts:
        raise IbmLoaderError("The IBM file is empty.")
    return pd.concat(parts, ignore_index=True), source_rows


# --- Persist + one-call entry point -------------------------------------------

def persist_ibm(sample: IbmSample, dataset_id: str = DATASET_ID) -> None:
    """Replace the active dataset with the sample (LLM cache preserved)."""
    clear_data(keep_llm_cache=True)
    with session_scope() as session:
        session.bulk_insert_mappings(Account, sample.accounts)
        session.bulk_insert_mappings(
            Transaction, [{**t, "dataset_id": dataset_id} for t in sample.txns])


def load_ibm_subset(path: Path | None = None, rules: Rules | None = None,
                    persist: bool = True) -> IbmSample:
    """Load, sample and (optionally) persist the IBM AML HI-Small dataset.

    Downloads the file first if it is not already in ``data/``.
    """
    cfg = (rules or load_rules()).ingest.ibm
    csv_path = path or download_hi_small()
    try:
        cleaned, source_rows = read_hi_small(csv_path, cfg.currency)
    except (ValueError, KeyError) as exc:
        raise IbmLoaderError(f"Unexpected IBM file format ({type(exc).__name__}). "
                             "Expected the 11-column HI-Small_Trans.csv.") from None
    sample = sample_ibm(cleaned, max_transactions=cfg.max_transactions,
                        context_share=cfg.context_share, seed=cfg.seed,
                        source_rows=source_rows)
    if persist:
        persist_ibm(sample)
    return sample
