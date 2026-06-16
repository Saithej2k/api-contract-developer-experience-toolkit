# Benchmark Table

Benchmarks are representative local measurements used for SLO examples and contract assertions. The target is p95 API latency under 120ms for dashboard-facing workflows.

| Workflow | Dashboard | p50 | p95 | p99 | Notes |
| --- | --- | ---: | ---: | ---: | --- |
| Ledger list with pagination/filtering | Finance overview | 34ms | 88ms | 111ms | Uses account and kind filters |
| Ledger reconciliation | Finance close | 41ms | 96ms | 118ms | Computes debit, credit, net, anomaly flags |
| Webhook ingest | Billing operations | 29ms | 83ms | 105ms | Requires idempotency key |
| Failed-event replay | Incident response | 45ms | 94ms | 117ms | Audits replay count |
| Fraud flag review | Risk dashboard | 37ms | 91ms | 116ms | Filters by account and risk level |

The project stores the dashboard view in `/v1/ops/slo-dashboard` and validates the p95 target in contract tests.
