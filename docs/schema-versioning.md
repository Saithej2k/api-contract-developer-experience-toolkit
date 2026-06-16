# Schema Versioning

The API accepts an optional `X-Schema-Version` request header. Supported versions are visible through:

```bash
curl -H "X-API-Key: admin-key" http://127.0.0.1:8000/v1/schemas/versions
```

## Current Policy

- Current write version: `2025-02-01`
- Deprecated readable version: `2024-09-01`
- Unknown schema versions return `UNSUPPORTED_SCHEMA_VERSION`
- Additive request fields must be optional or have server defaults
- Response fields may be added when generated clients are regenerated in the same change set

## Migration Example

`2024-09-01` ledger writes:

```json
{
  "external_id": "txn_1001",
  "account_id": "acct_ledger",
  "kind": "credit",
  "amount_cents": 4200
}
```

`2025-02-01` ledger writes can add `client_reference_id`, `risk_score`, and `metadata` without breaking older clients:

```json
{
  "external_id": "txn_1001",
  "account_id": "acct_ledger",
  "kind": "credit",
  "amount_cents": 4200,
  "client_reference_id": "dashboard-row-884",
  "risk_score": 12,
  "metadata": {
    "workflow": "finance_overview"
  }
}
```

## Backward-Compatible API Changes

- Add optional request fields.
- Add response fields when OpenAPI and TypeScript clients are regenerated.
- Add enum values only behind a documented rollout plan.
- Keep old routes readable until the sunset date.
- Preserve the typed error envelope.
