"""SQLAlchemy 2.0 ORM models (ARCHITECTURE.md §4).

Portable types only (String, Integer, Float, DateTime, Text) so the same code
runs on SQLite today and SQL Server/Postgres by a ``DATABASE_URL`` change
(CLAUDE.md hard rule #8). JSON payloads are stored as ``Text`` and (de)serialised
by callers, keeping columns portable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all RingSight tables."""


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    bank: Mapped[str] = mapped_column(String(64))
    country: Mapped[str] = mapped_column(String(8))
    account_type: Mapped[str] = mapped_column(String(16))  # individual/business/merchant/payroll
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Transaction(Base):
    __tablename__ = "transactions"

    txn_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    sender_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.account_id"))
    receiver_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.account_id"))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    ts: Mapped[datetime] = mapped_column(DateTime)
    channel: Mapped[str] = mapped_column(String(32), default="transfer")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Ground-truth labels (nullable — real uploads have none).
    is_laundering: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gt_pattern: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gt_ring_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dataset_id: Mapped[str] = mapped_column(String(64), default="default")


class Identifier(Base):
    __tablename__ = "identifiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.account_id"))
    id_type: Mapped[str] = mapped_column(String(16))  # ip | device | phone
    value: Mapped[str] = mapped_column(String(64))


class DetectionRun(Base):
    __tablename__ = "detection_runs"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    n_txns: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class AlertRow(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("detection_runs.run_id"))
    pattern: Mapped[str] = mapped_column(String(32))
    accounts_json: Mapped[str] = mapped_column(Text, default="[]")
    txn_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="medium")


class CaseRow(Base):
    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("detection_runs.run_id"))
    title: Mapped[str] = mapped_column(String(256), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="New")
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    patterns_json: Mapped[str] = mapped_column(Text, default="[]")
    accounts_json: Mapped[str] = mapped_column(Text, default="[]")
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    n_txns: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CaseAccount(Base):
    __tablename__ = "case_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(16), ForeignKey("cases.case_id"))
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.account_id"))
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    explanation_json: Mapped[str] = mapped_column(Text, default="[]")


class Evidence(Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(16), ForeignKey("cases.case_id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # txn | identifier | metric | pattern
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class SarDraft(Base):
    __tablename__ = "sar_drafts"

    draft_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(16), ForeignKey("cases.case_id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    typology_json: Mapped[str] = mapped_column(Text, default="{}")
    narrative_json: Mapped[str] = mapped_column(Text, default="{}")
    grounding_score: Mapped[float] = mapped_column(Float, default=0.0)
    model_used: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    case_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    row_hash: Mapped[str] = mapped_column(String(64), default="")


class LlmCache(Base):
    __tablename__ = "llm_cache"

    prompt_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(32))
    prompt_version: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    response_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class DecisionLog(Base):
    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(16))
    draft_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    step: Mapped[str] = mapped_column(String(32))
    signals_json: Mapped[str] = mapped_column(Text, default="{}")
    outcome: Mapped[str] = mapped_column(String(32))  # drafted | needs_more_evidence | escalated
    created_at: Mapped[datetime] = mapped_column(DateTime)
