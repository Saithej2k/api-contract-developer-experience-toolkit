from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.errors import ErrorResponse, ApiError, ErrorCode
from backend.app.core.security import Principal, require_permission
from backend.app.db import get_db
from backend.app.models import AuditLog, FraudFlag, LedgerEntry, WebhookEvent
from backend.app.schemas import (
    AuditLogPage,
    EventStatus,
    FraudFlagRead,
    LedgerEntryCreate,
    LedgerEntryPage,
    LedgerKind,
    LedgerReconciliationSummary,
    SchemaVersionInfo,
    SLODashboard,
    SLOMetric,
    WebhookEventCreate,
    WebhookEventPage,
    WebhookEventRead,
    WebhookReplayRequest,
    WebhookReplayResult,
)
from backend.app.services import (
    as_audit_log,
    as_fraud_flag,
    as_ledger,
    as_webhook_event,
    audit,
    create_fraud_flags_for_entry,
    get_idempotent_replay,
    mark_webhook_failed,
    mark_webhook_processed,
    paginate,
    store_idempotent_response,
    validate_schema_version,
)

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "Forbidden"},
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conflict"},
    422: {"model": ErrorResponse, "description": "Validation failed"},
}

router = APIRouter(prefix="/v1", tags=["v1"])


@router.get("/schemas/versions", response_model=SchemaVersionInfo, responses=ERROR_RESPONSES)
def get_schema_versions(
    principal: Principal = Depends(require_permission("slo:read")),
) -> SchemaVersionInfo:
    return SchemaVersionInfo(
        current=settings.current_schema_version,
        supported=list(settings.supported_schema_versions),
        deprecated=list(settings.deprecated_schema_versions),
        backward_compatible_changes=[
            "Optional client_reference_id added to ledger writes.",
            "Fraud risk_score became optional with default 0.",
            "Webhook payload accepts additive metadata fields.",
        ],
        deprecation_notes=[
            "Schema 2024-09-01 remains readable but new writes should use 2025-02-01.",
            "GET /v1/legacy/transactions is deprecated in favor of /v1/ledger/entries.",
        ],
    )


@router.get("/ops/slo-dashboard", response_model=SLODashboard, responses=ERROR_RESPONSES)
def get_slo_dashboard(
    principal: Principal = Depends(require_permission("slo:read")),
) -> SLODashboard:
    return SLODashboard(
        service=settings.app_name,
        window="rolling_7d",
        latency_p50_ms=38,
        latency_p95_ms=94,
        latency_p99_ms=118,
        error_rate=0.002,
        availability=99.96,
        metrics=[
            SLOMetric(name="p95 latency", target="<120ms", current="94ms", status="healthy"),
            SLOMetric(name="contract test pass rate", target="100%", current="100%", status="healthy"),
            SLOMetric(name="failed event replay lag", target="<5m", current="2m", status="healthy"),
        ],
    )


@router.get("/ledger/entries", response_model=LedgerEntryPage, responses=ERROR_RESPONSES)
def list_ledger_entries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    account_id: str | None = None,
    kind: LedgerKind | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("ledger:read")),
) -> LedgerEntryPage:
    statement = select(LedgerEntry)
    if account_id:
        statement = statement.where(LedgerEntry.account_id == account_id)
    if kind:
        statement = statement.where(LedgerEntry.kind == kind.value)
    statement = statement.order_by(desc(LedgerEntry.created_at))
    entries, meta = paginate(db, statement, page, page_size)
    return LedgerEntryPage(items=[as_ledger(entry) for entry in entries], meta=meta)


@router.post(
    "/ledger/entries",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_ledger_entry(
    payload: LedgerEntryCreate,
    response: Response,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    x_schema_version: str | None = Header(default=None, alias="X-Schema-Version"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("ledger:write")),
):
    schema_version = validate_schema_version(x_schema_version)
    path = "/v1/ledger/entries"
    payload_json = payload.model_dump(mode="json")
    replay = get_idempotent_replay(db, x_idempotency_key, "POST", path, payload_json)
    if replay:
        return JSONResponse(
            status_code=replay.response_status,
            content=replay.response_body,
            headers={"X-Idempotent-Replay": "true", "X-Schema-Version": schema_version},
        )

    entry = LedgerEntry(
        external_id=payload.external_id,
        account_id=payload.account_id,
        kind=payload.kind.value,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        description=payload.description,
        risk_score=payload.risk_score,
        schema_version=schema_version,
        meta={
            **payload.metadata,
            **({"client_reference_id": payload.client_reference_id} if payload.client_reference_id else {}),
        },
    )
    db.add(entry)
    db.flush()
    flags = create_fraud_flags_for_entry(db, entry)
    audit(
        db,
        principal,
        action="ledger.entry.created",
        resource_type="ledger_entry",
        resource_id=entry.id,
        metadata={"idempotency_key": x_idempotency_key, "fraud_flags": len(flags)},
    )
    body = as_ledger(entry).model_dump(mode="json")
    store_idempotent_response(db, x_idempotency_key or "", "POST", path, payload_json, 201, body)
    db.commit()
    response.headers["X-Schema-Version"] = schema_version
    return body


@router.get(
    "/ledger/reconciliation",
    response_model=LedgerReconciliationSummary,
    responses=ERROR_RESPONSES,
)
def reconcile_ledger(
    account_id: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("ledger:read")),
) -> LedgerReconciliationSummary:
    statement = select(LedgerEntry)
    if account_id:
        statement = statement.where(LedgerEntry.account_id == account_id)
    entries = list(db.scalars(statement).all())
    debit = sum(entry.amount_cents for entry in entries if entry.kind == "debit")
    credit = sum(entry.amount_cents for entry in entries if entry.kind == "credit")
    net = credit - debit
    flags: list[str] = []
    if abs(net) > 50_000:
        flags.append("net_imbalance_exceeds_threshold")
    if any(entry.risk_score >= 85 for entry in entries):
        flags.append("contains_high_risk_entries")
    return LedgerReconciliationSummary(
        account_id=account_id,
        debit_cents=debit,
        credit_cents=credit,
        net_cents=net,
        entry_count=len(entries),
        anomaly_flags=flags,
    )


@router.get(
    "/legacy/transactions",
    response_model=LedgerEntryPage,
    deprecated=True,
    responses=ERROR_RESPONSES,
)
def list_legacy_transactions(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("ledger:read")),
) -> LedgerEntryPage:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-12-31"
    response.headers["Link"] = '</v1/ledger/entries>; rel="successor-version"'
    entries, meta = paginate(db, select(LedgerEntry).order_by(desc(LedgerEntry.created_at)), page, page_size)
    return LedgerEntryPage(items=[as_ledger(entry) for entry in entries], meta=meta)


@router.post(
    "/webhooks/events",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
def ingest_webhook_event(
    payload: WebhookEventCreate,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    x_schema_version: str | None = Header(default=None, alias="X-Schema-Version"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("webhooks:write")),
):
    schema_version = validate_schema_version(x_schema_version)
    path = "/v1/webhooks/events"
    payload_json = payload.model_dump(mode="json")
    replay = get_idempotent_replay(db, x_idempotency_key, "POST", path, payload_json)
    if replay:
        return JSONResponse(
            status_code=replay.response_status,
            content=replay.response_body,
            headers={"X-Idempotent-Replay": "true", "X-Schema-Version": schema_version},
        )

    event = WebhookEvent(
        source=payload.source,
        event_type=payload.event_type,
        idempotency_key=x_idempotency_key or "",
        payload=payload.payload,
        schema_version=schema_version,
    )
    if payload.simulate_failure:
        mark_webhook_failed(event, "Simulated downstream processing failure.")
    else:
        mark_webhook_processed(event)
    db.add(event)
    db.flush()
    audit(
        db,
        principal,
        action="webhook.event.ingested",
        resource_type="webhook_event",
        resource_id=event.id,
        metadata={"status": event.status, "idempotency_key": x_idempotency_key},
    )
    body = as_webhook_event(event).model_dump(mode="json")
    store_idempotent_response(db, x_idempotency_key or "", "POST", path, payload_json, 202, body)
    db.commit()
    return body


@router.get("/webhooks/events", response_model=WebhookEventPage, responses=ERROR_RESPONSES)
def list_webhook_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status_filter: EventStatus | None = Query(default=None, alias="status"),
    source: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("webhooks:read")),
) -> WebhookEventPage:
    statement = select(WebhookEvent)
    if status_filter:
        statement = statement.where(WebhookEvent.status == status_filter.value)
    if source:
        statement = statement.where(WebhookEvent.source == source)
    statement = statement.order_by(desc(WebhookEvent.received_at))
    events, meta = paginate(db, statement, page, page_size)
    return WebhookEventPage(items=[as_webhook_event(event) for event in events], meta=meta)


@router.post(
    "/webhooks/events/{event_id}/replay",
    response_model=WebhookEventRead,
    responses=ERROR_RESPONSES,
)
def replay_failed_event(
    event_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("webhooks:replay")),
) -> WebhookEventRead:
    event = db.get(WebhookEvent, event_id)
    if not event:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.not_found,
            message="Webhook event was not found.",
            details={"event_id": event_id},
        )
    if event.status != "failed":
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.replay_not_allowed,
            message="Only failed events can be replayed.",
            details={"status": event.status},
        )
    event.replay_count += 1
    mark_webhook_processed(event)
    audit(
        db,
        principal,
        action="webhook.event.replayed",
        resource_type="webhook_event",
        resource_id=event.id,
        metadata={"replay_count": event.replay_count},
    )
    db.commit()
    return as_webhook_event(event)


@router.post("/webhooks/replays", response_model=WebhookReplayResult, responses=ERROR_RESPONSES)
def replay_failed_events(
    payload: WebhookReplayRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("webhooks:replay")),
) -> WebhookReplayResult:
    statement = select(WebhookEvent).where(WebhookEvent.status == "failed")
    if payload.source:
        statement = statement.where(WebhookEvent.source == payload.source)
    if payload.event_type:
        statement = statement.where(WebhookEvent.event_type == payload.event_type)
    events = list(db.scalars(statement.limit(payload.max_events)).all())
    event_ids: list[str] = []
    for event in events:
        event.replay_count += 1
        mark_webhook_processed(event)
        event_ids.append(event.id)
        audit(
            db,
            principal,
            action="webhook.event.replayed",
            resource_type="webhook_event",
            resource_id=event.id,
            metadata={"bulk": True, "source": payload.source, "event_type": payload.event_type},
        )
    db.commit()
    return WebhookReplayResult(replayed=len(event_ids), skipped=0, event_ids=event_ids)


@router.get("/fraud/flags", response_model=list[FraudFlagRead], responses=ERROR_RESPONSES)
def list_fraud_flags(
    account_id: str | None = None,
    risk_level: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("fraud:read")),
) -> list[FraudFlagRead]:
    statement = select(FraudFlag).order_by(desc(FraudFlag.created_at))
    if account_id:
        statement = statement.where(FraudFlag.account_id == account_id)
    if risk_level:
        statement = statement.where(FraudFlag.risk_level == risk_level)
    return [as_fraud_flag(flag) for flag in db.scalars(statement).all()]


@router.get("/audit/logs", response_model=AuditLogPage, responses=ERROR_RESPONSES)
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("audit:read")),
) -> AuditLogPage:
    logs, meta = paginate(db, select(AuditLog).order_by(desc(AuditLog.created_at)), page, page_size)
    return AuditLogPage(items=[as_audit_log(log) for log in logs], meta=meta)
