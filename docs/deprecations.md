# Deprecation Notes

`GET /v1/legacy/transactions` is deprecated and remains available until `2026-12-31`.

Replacement:

```text
GET /v1/ledger/entries
```

The deprecated endpoint returns:

- `Deprecation: true`
- `Sunset: 2026-12-31`
- `Link: </v1/ledger/entries>; rel="successor-version"`

## Review Rules

- Every deprecated endpoint must name a successor.
- Contract tests must assert the deprecation headers.
- API docs must include the sunset date.
- Generated clients should expose the replacement path before the old path is removed.
