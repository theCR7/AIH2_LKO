"""CSV upload loader with column mapping and friendly validation (PRD F1.2/F1.3).

Validation errors are *returned as a list* rather than raised, so the Streamlit
UI can show friendly messages and never crash (CLAUDE.md: no exceptions to UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from core.db import session_scope
from core.models import Account, Transaction
from core.utils import utcnow

# Target field -> whether it is required in the mapping.
REQUIRED_FIELDS = ["sender", "receiver", "amount", "timestamp"]
OPTIONAL_FIELDS = ["currency", "channel", "ip", "device_id"]


@dataclass
class LoadResult:
    """Outcome of a CSV load attempt."""

    ok: bool
    n_txns: int = 0
    n_accounts: int = 0
    errors: list[str] = field(default_factory=list)
    preview: pd.DataFrame | None = None


def _parse_ts(value: object) -> datetime | None:
    """Parse a timestamp cell, returning None if unparseable."""
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except (ValueError, TypeError):
        return None


def validate_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> list[str]:
    """Check the column mapping covers required fields and columns exist."""
    errors: list[str] = []
    for fld in REQUIRED_FIELDS:
        col = mapping.get(fld)
        if not col:
            errors.append(f"Missing mapping for required field '{fld}'.")
        elif col not in df.columns:
            errors.append(f"Mapped column '{col}' for '{fld}' not found in CSV.")
    return errors


def load_dataframe(df: pd.DataFrame, mapping: dict[str, str], dataset_id: str = "upload",
                   persist: bool = True) -> LoadResult:
    """Validate and load a transactions dataframe using a column mapping.

    Args:
        df: the raw uploaded dataframe.
        mapping: maps logical field -> actual CSV column name. Keys may include
            ``sender``, ``receiver``, ``amount``, ``timestamp`` (required) and
            ``currency``, ``channel``, ``ip``, ``device_id`` (optional).
        dataset_id: logical dataset name to tag rows with.
        persist: write parsed rows to the DB.
    """
    errors = validate_mapping(df, mapping)
    if errors:
        return LoadResult(ok=False, errors=errors)

    rows: list[dict] = []
    account_ids: set[str] = set()
    row_errors: list[str] = []

    for idx, raw in df.iterrows():
        sender = str(raw[mapping["sender"]]).strip()
        receiver = str(raw[mapping["receiver"]]).strip()
        ts = _parse_ts(raw[mapping["timestamp"]])
        try:
            amount = float(raw[mapping["amount"]])
        except (ValueError, TypeError):
            amount = float("nan")

        line = int(idx) + 2  # +1 for header, +1 for 1-based
        if not sender or not receiver:
            row_errors.append(f"Row {line}: missing sender/receiver.")
            continue
        if ts is None:
            row_errors.append(f"Row {line}: bad or missing timestamp.")
            continue
        if amount != amount or amount < 0:  # NaN or negative
            row_errors.append(f"Row {line}: amount must be a non-negative number.")
            continue

        account_ids.update([sender, receiver])
        rows.append(
            {
                "txn_id": f"T{len(rows) + 1:06d}",
                "sender_id": sender,
                "receiver_id": receiver,
                "amount": round(amount, 2),
                "currency": str(raw[mapping["currency"]]) if mapping.get("currency") else "USD",
                "ts": ts,
                "channel": str(raw[mapping["channel"]]) if mapping.get("channel") else "transfer",
                "ip": str(raw[mapping["ip"]]) if mapping.get("ip") else None,
                "device_id": (str(raw[mapping["device_id"]])
                              if mapping.get("device_id") else None),
                "is_laundering": None,
                "gt_pattern": None,
                "gt_ring_id": None,
                "dataset_id": dataset_id,
            }
        )

    if not rows:
        return LoadResult(ok=False, errors=row_errors or ["No valid rows found in CSV."])

    if persist:
        _persist_upload(rows, sorted(account_ids), dataset_id)

    preview = pd.DataFrame(rows[:50])
    return LoadResult(ok=True, n_txns=len(rows), n_accounts=len(account_ids),
                      errors=row_errors, preview=preview)


def _persist_upload(rows: list[dict], account_ids: list[str], dataset_id: str) -> None:
    """Persist uploaded txns and auto-create minimal account records.

    The DB holds one active dataset, so any prior dataset is cleared first: upload
    transaction ids (``T000001`` …) are a global PK and would otherwise collide
    with the sample dataset, and a prior run's identifiers/accounts would leak into
    detection. The LLM cache is preserved.
    """
    from core.db import clear_data
    clear_data(keep_llm_cache=True)
    now = utcnow()
    accounts = [
        {
            "account_id": aid, "name": aid, "bank": "unknown", "country": "NA",
            "account_type": "individual", "created_at": now,
        }
        for aid in account_ids
    ]
    with session_scope() as session:
        session.bulk_insert_mappings(Account, accounts)
        session.bulk_insert_mappings(Transaction, rows)


def load_csv(path: str, mapping: dict[str, str], dataset_id: str = "upload",
             persist: bool = True) -> LoadResult:
    """Load a CSV file from disk (convenience wrapper over :func:`load_dataframe`)."""
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        return LoadResult(ok=False, errors=[f"Could not read CSV: {exc}"])
    return load_dataframe(df, mapping, dataset_id=dataset_id, persist=persist)
