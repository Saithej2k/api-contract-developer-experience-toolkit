from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.errors import ApiError, ErrorCode
from backend.app.core.security import Principal
from backend.app.models import AuditLog, FraudFlag, IdempotencyRecord, LedgerEntry, WebhookEvent
from backend.app.schemas import (
    AuditLogRead,
    FraudFlagRead,
    LedgerEntryRead,
    PageMeta,
    WebhookEventRead,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_ledger(entry: LedgerEntry) -> LedgerEntryRead:
    return LedgerEntryRead(
        id=entry.id,
        external_id=entry.external_id,
        account_id=entry.account_id,
        kind=entry.kind,
        amount_cents=entry.amount_cents,
        currency=entry.currency,
        description=entry.description,
        risk_score=entry.risk_score,
        schema_version=entry.schema_version,
        metadata=entry.meta,
        created_at=entry.created_at,
    )


def as_webhook_event(event: WebhookEvent) -> WebhookEventRead:
    return WebhookEventRead(
        id=event.id,
        source=event.source,
        event_type=event.event_type,
        idempotency_key=event.idempotency_key,
        status=event.status,
        payload=event.payload,
        schema_version=event.schema_version,
        replay_count=event.replay_count,
        next_retry_at=event.next_retry_at,
        last_error=event.last_error,
        received_at=event.received_at,
        processed_at=event.processed_at,
    )


def as_fraud_flag(flag: FraudFlag) -> FraudFlagRead:
    return FraudFlagRead(
        id=flag.id,
        ledger_entry_id=flag.ledger_entry_id,
        event_id=flag.event_id,
        account_id=flag.account_id,
        risk_level=flag.risk_level,
        reason=flag.reason,
        status=flag.status,
        created_at=flag.created_at,
    )


def as_audit_log(log: AuditLog) -> AuditLogRead:
    return AuditLogRead(
        id=log.id,
        actor=log.actor,
        role=log.role,
        action=log.action,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        metadata=log.meta,
        created_at=log.created_at,
    )


def page_meta(page: int, page_size: int, total: int) -> PageMeta:
    return PageMeta(
        page=page,
        page_size=page_size,
        total=total,
        has_next=page * page_size < total,
    )


def paginate(db: Session, statement: Select, page: int, page_size: int) -> tuple[list[Any], PageMeta]:
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(
        statement.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), page_meta(page, page_size, total)


def validate_schema_version(schema_version: str | None) -> str:
    version = schema_version or settings.current_schema_version
    if version not in settings.supported_schema_versions:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.unsupported_schema_version,
            message="Unsupported schema version.",
            details={
                "requested": version,
                "supported": list(settings.supported_schema_versions),
            },
        )
    return version


def request_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_idempotent_replay(
    db: Session,
    key: str | None,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> IdempotencyRecord | None:
    if not key:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.idempotency_key_required,
            message="X-Idempotency-Key is required for write endpoints.",
        )

    payload_hash = request_hash(payload)
    record = db.get(IdempotencyRecord, key)
    if not record:
        return None

    if record.method != method or record.path != path or record.request_hash != payload_hash:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.idempotency_conflict,
            message="Idempotency key was reused with a different request.",
            details={"key": key},
        )
    return record


def store_idempotent_response(
    db: Session,
    key: str,
    method: str,
    path: str,
    payload: dict[str, Any],
    response_status: int,
    response_body: dict[str, Any],
) -> None:
    db.add(
        IdempotencyRecord(
            key=key,
            method=method,
            path=path,
            request_hash=request_hash(payload),
            response_status=response_status,
            response_body=response_body,
        )
    )


def audit(
    db: Session,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor=principal.actor,
            role=principal.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            meta=metadata or {},
        )
    )


def exponential_backoff_seconds(attempt: int) -> int:
    return min(300, 2 ** max(attempt, 1))


def mark_webhook_processed(event: WebhookEvent) -> None:
    event.status = "processed"
    event.last_error = None
    event.next_retry_at = None
    event.processed_at = utcnow()


def mark_webhook_failed(event: WebhookEvent, reason: str) -> None:
    event.status = "failed"
    event.last_error = reason
    event.replay_count = (event.replay_count or 0) + 1
    event.next_retry_at = utcnow() + timedelta(seconds=exponential_backoff_seconds(event.replay_count))


def create_fraud_flags_for_entry(db: Session, entry: LedgerEntry) -> list[FraudFlag]:
    flags: list[FraudFlag] = []
    if entry.amount_cents >= 100_000:
        flags.append(
            FraudFlag(
                ledger_entry_id=entry.id,
                account_id=entry.account_id,
                risk_level="high",
                reason="Large transaction exceeds review threshold.",
            )
        )
    if entry.risk_score >= 85:
        flags.append(
            FraudFlag(
                ledger_entry_id=entry.id,
                account_id=entry.account_id,
                risk_level="critical",
                reason="Client supplied fraud/anomaly risk score is elevated.",
            )
        )
    for flag in flags:
        db.add(flag)
    return flags
