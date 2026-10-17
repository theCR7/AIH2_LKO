"""Tamper-evident audit logging (BR4 / PRD F6.2).

Appends audit rows chained by sha256 so any edit to history is detectable
(verify with ``python -m core.db --verify-audit``). Portable SQLAlchemy only.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from core.db import audit_row_hash
from core.models import AuditLog
from core.utils import utcnow


def record_audit(session: Session, actor: str, action: str, case_id: str | None,
                 before: dict | None = None, after: dict | None = None) -> AuditLog:
    """Append one audit entry, chaining its hash from the previous row."""
    before_json = json.dumps(before or {}, sort_keys=True)
    after_json = json.dumps(after or {}, sort_keys=True)
    ts = utcnow()
    last = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = last.row_hash if last else ""
    row_hash = audit_row_hash(prev_hash, actor, action, case_id,
                              before_json, after_json, ts.isoformat())
    entry = AuditLog(ts=ts, actor=actor, action=action, case_id=case_id,
                     before_json=before_json, after_json=after_json,
                     prev_hash=prev_hash, row_hash=row_hash)
    session.add(entry)
    return entry
