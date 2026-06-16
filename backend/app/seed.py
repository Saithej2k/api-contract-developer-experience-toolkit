from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import Principal
from backend.app.models import FraudFlag, LedgerEntry, WebhookEvent
from backend.app.services import audit, create_fraud_flags_for_entry, mark_webhook_failed, mark_webhook_processed


def seed_database(db: Session) -> None:
    if db.scalar(select(LedgerEntry).limit(1)):
        return

    principal = Principal(actor="seed-script", role="admin")
    entries = [
        LedgerEntry(
            external_id="seed-ledger-001",
            account_id="acct-dashboard-na",
            kind="credit",
            amount_cents=185_000,
            currency="USD",
            description="Dashboard subscription revenue",
            risk_score=12,
            schema_version=settings.current_schema_version,
            meta={"workflow": "finance_overview"},
        ),
        LedgerEntry(
            external_id="seed-ledger-002",
            account_id="acct-dashboard-na",
            kind="debit",
            amount_cents=24_500,
            currency="USD",
            description="Refund batch",
            risk_score=18,
            schema_version=settings.current_schema_version,
            meta={"workflow": "refunds"},
        ),
        LedgerEntry(
            external_id="seed-ledger-003",
            account_id="acct-dashboard-eu",
            kind="debit",
            amount_cents=121_000,
            currency="USD",
            description="Manual adjustment",
            risk_score=91,
            schema_version=settings.current_schema_version,
            meta={"workflow": "risk_review"},
        ),
    ]
    for entry in entries:
        db.add(entry)
        db.flush()
        create_fraud_flags_for_entry(db, entry)
        audit(
            db,
            principal,
            action="ledger.entry.seeded",
            resource_type="ledger_entry",
            resource_id=entry.id,
            metadata={"external_id": entry.external_id},
        )

    processed = WebhookEvent(
        source="billing",
        event_type="invoice.paid",
        idempotency_key="seed-webhook-processed",
        payload={"invoice_id": "inv_seed_001", "amount_cents": 185_000},
        schema_version=settings.current_schema_version,
    )
    mark_webhook_processed(processed)
    failed = WebhookEvent(
        source="risk-engine",
        event_type="review.created",
        idempotency_key="seed-webhook-failed",
        payload={"review_id": "risk_seed_001"},
        schema_version=settings.current_schema_version,
    )
    mark_webhook_failed(failed, "Seeded failed event for replay workflow.")
    db.add_all([processed, failed])
    db.flush()
    db.add(
        FraudFlag(
            event_id=failed.id,
            account_id="acct-dashboard-eu",
            risk_level="medium",
            reason="Risk-engine webhook failed before review creation.",
        )
    )
    audit(
        db,
        principal,
        action="webhook.event.seeded",
        resource_type="webhook_event",
        resource_id=failed.id,
        metadata={"status": failed.status},
    )
