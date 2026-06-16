# Review Checklists

## API Contract Review

- Endpoint is versioned under `/v1`.
- Request and response models are present in OpenAPI.
- Error responses use `ErrorResponse`.
- Pagination and filters follow existing conventions.
- Schema-version behavior is documented.
- Deprecation headers are tested when a route is being replaced.

## Developer Experience Review

- `docs/openapi.json` is regenerated.
- `client/src/generated/schema.ts` is regenerated.
- TypeScript client helpers compile.
- Jest covers client retry/backoff and typed errors.
- Playwright covers a live API contract workflow.

## Operations Review

- Idempotency keys are required for write endpoints.
- Webhook replay is bounded and audited.
- Failed events expose retry count and next retry time.
- Ledger reconciliation includes anomaly flags.
- SLO dashboard shows target and current p95 latency.
- RBAC permissions match the workflow owner.
