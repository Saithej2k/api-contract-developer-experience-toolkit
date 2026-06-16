# Operations

## Idempotency Keys

Write endpoints require `X-Idempotency-Key`. Reusing the same key with the same payload returns the original response. Reusing the key with a different payload returns `IDEMPOTENCY_CONFLICT`.

## Webhook Replay

- `POST /v1/webhooks/events` ingests events and can simulate downstream failures for contract testing.
- `POST /v1/webhooks/events/{event_id}/replay` replays one failed event.
- `POST /v1/webhooks/replays` replays a bounded batch of failed events by source or event type.

## Retry/Backoff Handling

The TypeScript client retries transient statuses with exponential backoff. Backend failed events store `next_retry_at` and `replay_count` so operators can inspect replay lag.

## Ledger Reconciliation

`GET /v1/ledger/reconciliation` computes debit, credit, net balance, entry count, and anomaly flags. The seeded data includes a high-risk account so the contract tests can validate reconciliation flags.

## Fraud/Anomaly Flags

Large ledger entries and elevated `risk_score` values create fraud flags. Admin and analyst roles can read these through `GET /v1/fraud/flags`.

## Audit Logs and RBAC

Audit logs are written for ledger creation, webhook ingest, seed events, and replay actions. Only the admin role can read audit logs.
