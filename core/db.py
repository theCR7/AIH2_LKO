"""Database engine, session factory and schema lifecycle.

SQLAlchemy 2.0 engine built from ``DATABASE_URL`` (SQLite default). Provides
``init_db()`` / ``reset_db()`` and a CLI:

    python -m core.db --reset        # drop + recreate all tables
    python -m core.db --verify-audit # verify the audit-log hash chain

Only portable SQLAlchemy constructs are used (CLAUDE.md hard rule #8).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import PROJECT_ROOT, load_settings
from core.models import AuditLog, Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _resolve_sqlite_path(url: str) -> str:
    """Make a relative SQLite path absolute and ensure its folder exists.

    Keeps the app working regardless of the current working directory and
    guarantees ``data/`` exists on a fresh clone.
    """
    prefix = "sqlite:///"
    if url.startswith(prefix):
        rel = url[len(prefix) :]
        path = Path(rel)
        if not path.is_absolute():
            path = PROJECT_ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"{prefix}{path}"
    return url


def get_engine() -> Engine:
    """Return a lazily-created singleton engine."""
    global _engine, _SessionLocal
    if _engine is None:
        url = _resolve_sqlite_path(load_settings().database_url)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, connect_args=connect_args)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Return the configured session factory (creating the engine if needed)."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context manager: commit on success, rollback on error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(get_engine())


def reset_db() -> None:
    """Drop and recreate all tables (destructive)."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


# --- Audit-log hash chain (BR4: tamper-evident) ------------------------------


def audit_row_hash(prev_hash: str, actor: str, action: str, case_id: str | None,
                   before_json: str, after_json: str, ts_iso: str) -> str:
    """Compute the sha256 hash for an audit row, chaining from ``prev_hash``."""
    payload = json.dumps(
        {
            "prev": prev_hash,
            "actor": actor,
            "action": action,
            "case_id": case_id,
            "before": before_json,
            "after": after_json,
            "ts": ts_iso,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_audit_chain() -> tuple[bool, int]:
    """Verify the audit-log hash chain.

    Returns ``(ok, n_rows)``. ``ok`` is False if any row's stored hash does not
    match a recomputation from its predecessor.
    """
    with session_scope() as session:
        rows = session.query(AuditLog).order_by(AuditLog.id).all()
        prev = ""
        for row in rows:
            expected = audit_row_hash(
                prev, row.actor, row.action, row.case_id,
                row.before_json, row.after_json, row.ts.isoformat(),
            )
            if expected != row.row_hash or row.prev_hash != prev:
                return False, len(rows)
            prev = row.row_hash
        return True, len(rows)


def _main() -> None:
    parser = argparse.ArgumentParser(description="RingSight DB utilities")
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    parser.add_argument("--init", action="store_true", help="create tables if missing")
    parser.add_argument("--verify-audit", action="store_true", help="verify audit hash chain")
    args = parser.parse_args()

    if args.reset:
        reset_db()
        print("Database reset: all tables dropped and recreated.")
    elif args.init:
        init_db()
        print("Database initialised.")
    elif args.verify_audit:
        ok, n = verify_audit_chain()
        print(f"Audit chain {'OK' if ok else 'BROKEN'} over {n} rows.")
    else:
        parser.print_help()


if __name__ == "__main__":
    _main()
