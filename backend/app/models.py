from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("external_id", name="uq_ledger_entries_external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    account_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    description: Mapped[str | None] = mapped_column(String(240), nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(24), nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(140), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, default="pending")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(24), nullable=False)
    replay_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FraudFlag(Base):
    __tablename__ = "fraud_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ledger_entry_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    account_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(120), nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(140), primary_key=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(240), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
