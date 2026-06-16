from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LedgerKind(str, Enum):
    debit = "debit"
    credit = "credit"


class EventStatus(str, Enum):
    pending = "pending"
    processed = "processed"
    failed = "failed"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class PageMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    has_next: bool


class LedgerEntryCreate(BaseModel):
    external_id: str = Field(min_length=3, max_length=80)
    account_id: str = Field(min_length=3, max_length=80)
    kind: LedgerKind
    amount_cents: int = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=240)
    risk_score: int = Field(default=0, ge=0, le=100)
    client_reference_id: str | None = Field(
        default=None,
        description="Backward-compatible optional field added in schema 2025-02-01.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str
    account_id: str
    kind: LedgerKind
    amount_cents: int
    currency: str
    description: str | None
    risk_score: int
    schema_version: str
    metadata: dict[str, Any]
    created_at: datetime


class LedgerEntryPage(BaseModel):
    items: list[LedgerEntryRead]
    meta: PageMeta


class WebhookEventCreate(BaseModel):
    source: str = Field(min_length=2, max_length=80)
    event_type: str = Field(min_length=3, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    simulate_failure: bool = Field(default=False)


class WebhookEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    event_type: str
    idempotency_key: str
    status: EventStatus
    payload: dict[str, Any]
    schema_version: str
    replay_count: int
    next_retry_at: datetime | None
    last_error: str | None
    received_at: datetime
    processed_at: datetime | None


class WebhookEventPage(BaseModel):
    items: list[WebhookEventRead]
    meta: PageMeta


class WebhookReplayRequest(BaseModel):
    source: str | None = None
    event_type: str | None = None
    max_events: int = Field(default=25, ge=1, le=100)


class WebhookReplayResult(BaseModel):
    replayed: int
    skipped: int
    event_ids: list[str]


class LedgerReconciliationSummary(BaseModel):
    account_id: str | None
    debit_cents: int
    credit_cents: int
    net_cents: int
    entry_count: int
    anomaly_flags: list[str]


class FraudFlagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ledger_entry_id: str | None
    event_id: str | None
    account_id: str
    risk_level: RiskLevel
    reason: str
    status: Literal["open", "reviewing", "closed"]
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor: str
    role: str
    action: str
    resource_type: str
    resource_id: str
    metadata: dict[str, Any]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogRead]
    meta: PageMeta


class SchemaVersionInfo(BaseModel):
    current: str
    supported: list[str]
    deprecated: list[str]
    backward_compatible_changes: list[str]
    deprecation_notes: list[str]


class SLOMetric(BaseModel):
    name: str
    target: str
    current: str
    status: Literal["healthy", "watch", "breached"]


class SLODashboard(BaseModel):
    service: str
    window: str
    latency_p50_ms: int
    latency_p95_ms: int
    latency_p99_ms: int
    error_rate: float
    availability: float
    metrics: list[SLOMetric]
