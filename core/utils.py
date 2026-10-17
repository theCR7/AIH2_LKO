"""Canonical formatting helpers (CLAUDE.md hard rule #14).

Narrative and reason text must use these exact formats so the SAR validator's
regexes (later phase) can parse them reliably:
- amounts: ``48,200.00 USD``
- dates:   ``2026-09-03``
- datetimes: ``2026-09-03 10:14``
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-naive datetime (DB convention)."""
    return datetime.now(UTC).replace(tzinfo=None)


def fmt_amount(amount: float, currency: str = "USD") -> str:
    """Format an amount as ``48,200.00 USD``."""
    return f"{amount:,.2f} {currency}"


def fmt_date(ts: datetime) -> str:
    """Format a date as ``2026-09-03``."""
    return ts.strftime("%Y-%m-%d")


def fmt_datetime(ts: datetime) -> str:
    """Format a datetime as ``2026-09-03 10:14``."""
    return ts.strftime("%Y-%m-%d %H:%M")
