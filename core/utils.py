"""Canonical formatting helpers (CLAUDE.md hard rule #14).

Narrative and reason text must use these exact formats so the SAR validator's
regexes can parse them reliably:
- amounts: ``48,200.00 USD`` (the code is the active dataset's currency)
- dates:   ``2026-09-03``
- datetimes: ``2026-09-03 10:14``
"""

from __future__ import annotations

from datetime import UTC, datetime

DEFAULT_CURRENCY = "USD"

_active_currency: str | None = None


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-naive datetime (DB convention)."""
    return datetime.now(UTC).replace(tzinfo=None)


def reset_currency_cache() -> None:
    """Forget the cached dataset currency (called whenever the loaded data changes)."""
    global _active_currency
    _active_currency = None


def active_currency() -> str:
    """The currency of the loaded dataset: its most common ``transactions.currency``.

    Datasets are single-currency by design (loaders keep one currency so amounts are
    comparable), so this is the one code every amount is printed with. Falls back to
    ``DEFAULT_CURRENCY`` when no data is loaded; an empty result is not cached.
    """
    global _active_currency
    if _active_currency is None:
        found = _lookup_currency()
        if found is None:
            return DEFAULT_CURRENCY
        _active_currency = found
    return _active_currency


def _lookup_currency() -> str | None:
    # Imported lazily: core.db imports this module's reset hook, so a top-level import
    # would be circular.
    try:
        from sqlalchemy import func, select

        from core.db import session_scope
        from core.models import Transaction

        with session_scope() as session:
            row = session.execute(
                select(Transaction.currency, func.count().label("n"))
                .group_by(Transaction.currency).order_by(func.count().desc()).limit(1)
            ).first()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def fmt_amount(amount: float, currency: str | None = None) -> str:
    """Format an amount as ``48,200.00 USD`` using the dataset's currency by default."""
    return f"{amount:,.2f} {currency or active_currency()}"


def fmt_date(ts: datetime) -> str:
    """Format a date as ``2026-09-03``."""
    return ts.strftime("%Y-%m-%d")


def fmt_datetime(ts: datetime) -> str:
    """Format a datetime as ``2026-09-03 10:14``."""
    return ts.strftime("%Y-%m-%d %H:%M")
