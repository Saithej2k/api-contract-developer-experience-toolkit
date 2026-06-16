from __future__ import annotations

from backend.app.services import exponential_backoff_seconds


def test_health_contract(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["schema_version"] == "2025-02-01"


def test_openapi_contains_versioned_paths_and_deprecation(client):
    response = client.get("/openapi.json")
    schema = response.json()
    assert "/v1/ledger/entries" in schema["paths"]
    assert schema["paths"]["/v1/legacy/transactions"]["get"]["deprecated"] is True


def test_openapi_exposes_typed_error_response(client):
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/v1/ledger/entries"]["get"]["responses"]
    assert responses["401"]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorResponse")


def test_auth_required_for_contract_endpoints(client):
    response = client.get("/v1/ledger/entries")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_MISSING"


def test_rbac_forbids_analyst_from_audit_logs(client, analyst_headers):
    response = client.get("/v1/audit/logs", headers=analyst_headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_ledger_pagination_contract(client, admin_headers):
    response = client.get("/v1/ledger/entries?page=1&page_size=2", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["meta"]["page"] == 1
    assert body["meta"]["has_next"] is True


def test_ledger_filtering_by_account_and_kind(client, admin_headers):
    response = client.get(
        "/v1/ledger/entries?account_id=acct-dashboard-na&kind=credit",
        headers=admin_headers,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert all(item["account_id"] == "acct-dashboard-na" for item in items)
    assert all(item["kind"] == "credit" for item in items)


def test_create_ledger_requires_idempotency_key(client, integration_headers):
    response = client.post(
        "/v1/ledger/entries",
        headers=integration_headers,
        json={
            "external_id": "contract-no-key",
            "account_id": "acct-contract",
            "kind": "credit",
            "amount_cents": 100,
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_create_ledger_replays_with_same_idempotency_key(client, integration_headers):
    headers = {**integration_headers, "X-Idempotency-Key": "ledger-contract-001"}
    payload = {
        "external_id": "contract-ledger-001",
        "account_id": "acct-contract",
        "kind": "credit",
        "amount_cents": 4200,
        "client_reference_id": "dash-001",
    }
    first = client.post("/v1/ledger/entries", headers=headers, json=payload)
    second = client.post("/v1/ledger/entries", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.headers["X-Idempotent-Replay"] == "true"
    assert first.json()["id"] == second.json()["id"]


def test_idempotency_key_conflict_is_typed(client, integration_headers):
    headers = {**integration_headers, "X-Idempotency-Key": "ledger-contract-conflict"}
    payload = {
        "external_id": "contract-ledger-conflict-1",
        "account_id": "acct-contract",
        "kind": "credit",
        "amount_cents": 4200,
    }
    assert client.post("/v1/ledger/entries", headers=headers, json=payload).status_code == 201
    payload["amount_cents"] = 4300
    response = client.post("/v1/ledger/entries", headers=headers, json=payload)
    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_validation_error_uses_standard_error_shape(client, integration_headers):
    response = client.post(
        "/v1/ledger/entries",
        headers={**integration_headers, "X-Idempotency-Key": "bad-ledger"},
        json={"external_id": "x", "account_id": "acct-contract", "kind": "credit", "amount_cents": -1},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_schema_version_header_is_reflected(client, integration_headers):
    response = client.post(
        "/v1/ledger/entries",
        headers={
            **integration_headers,
            "X-Idempotency-Key": "schema-ledger-001",
            "X-Schema-Version": "2024-09-01",
        },
        json={
            "external_id": "contract-ledger-schema",
            "account_id": "acct-contract",
            "kind": "credit",
            "amount_cents": 500,
        },
    )
    assert response.status_code == 201
    assert response.headers["X-Schema-Version"] == "2024-09-01"
    assert response.json()["schema_version"] == "2024-09-01"


def test_unsupported_schema_version_is_typed(client, integration_headers):
    response = client.post(
        "/v1/ledger/entries",
        headers={
            **integration_headers,
            "X-Idempotency-Key": "schema-ledger-unsupported",
            "X-Schema-Version": "2023-01-01",
        },
        json={
            "external_id": "contract-ledger-unsupported",
            "account_id": "acct-contract",
            "kind": "credit",
            "amount_cents": 500,
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_SCHEMA_VERSION"


def test_schema_versions_report_backward_compatible_changes(client, admin_headers):
    response = client.get("/v1/schemas/versions", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["current"] == "2025-02-01"
    assert body["backward_compatible_changes"]
    assert body["deprecation_notes"]


def test_legacy_endpoint_returns_deprecation_notes(client, admin_headers):
    response = client.get("/v1/legacy/transactions", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert "successor-version" in response.headers["Link"]


def test_webhook_ingest_processed_contract(client, integration_headers):
    response = client.post(
        "/v1/webhooks/events",
        headers={**integration_headers, "X-Idempotency-Key": "webhook-contract-processed"},
        json={"source": "billing", "event_type": "invoice.paid", "payload": {"invoice_id": "inv_001"}},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "processed"


def test_webhook_failure_sets_backoff(client, integration_headers):
    response = client.post(
        "/v1/webhooks/events",
        headers={**integration_headers, "X-Idempotency-Key": "webhook-contract-failed"},
        json={
            "source": "billing",
            "event_type": "invoice.failed",
            "payload": {"invoice_id": "inv_002"},
            "simulate_failure": True,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "failed"
    assert body["next_retry_at"] is not None
    assert body["last_error"]


def test_failed_event_replay_processes_event(client, integration_headers):
    created = client.post(
        "/v1/webhooks/events",
        headers={**integration_headers, "X-Idempotency-Key": "webhook-contract-replay-one"},
        json={
            "source": "risk-engine",
            "event_type": "review.created",
            "payload": {"review_id": "review_001"},
            "simulate_failure": True,
        },
    ).json()
    response = client.post(f"/v1/webhooks/events/{created['id']}/replay", headers=integration_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert response.json()["replay_count"] >= 2


def test_replay_nonexistent_event_returns_404(client, integration_headers):
    response = client.post("/v1/webhooks/events/missing/replay", headers=integration_headers)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_bulk_webhook_replay(client, integration_headers):
    client.post(
        "/v1/webhooks/events",
        headers={**integration_headers, "X-Idempotency-Key": "webhook-contract-replay-bulk"},
        json={
            "source": "risk-engine",
            "event_type": "review.updated",
            "payload": {"review_id": "review_002"},
            "simulate_failure": True,
        },
    )
    response = client.post(
        "/v1/webhooks/replays",
        headers=integration_headers,
        json={"source": "risk-engine", "max_events": 10},
    )
    assert response.status_code == 200
    assert response.json()["replayed"] >= 1


def test_ledger_reconciliation_reports_anomaly_flags(client, admin_headers):
    response = client.get("/v1/ledger/reconciliation?account_id=acct-dashboard-eu", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["entry_count"] >= 1
    assert "contains_high_risk_entries" in body["anomaly_flags"]


def test_fraud_flags_are_created_for_high_risk_ledger(client, integration_headers, admin_headers):
    client.post(
        "/v1/ledger/entries",
        headers={**integration_headers, "X-Idempotency-Key": "fraud-ledger-001"},
        json={
            "external_id": "fraud-ledger-contract",
            "account_id": "acct-fraud",
            "kind": "debit",
            "amount_cents": 250000,
            "risk_score": 95,
        },
    )
    response = client.get("/v1/fraud/flags?account_id=acct-fraud", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_slo_dashboard_p95_under_target(client, admin_headers):
    response = client.get("/v1/ops/slo-dashboard", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["latency_p95_ms"] < 120


def test_audit_logs_record_write_actions(client, integration_headers, admin_headers):
    client.post(
        "/v1/ledger/entries",
        headers={**integration_headers, "X-Idempotency-Key": "audit-ledger-001"},
        json={
            "external_id": "audit-ledger-contract",
            "account_id": "acct-audit",
            "kind": "credit",
            "amount_cents": 700,
        },
    )
    response = client.get("/v1/audit/logs", headers=admin_headers)
    assert response.status_code == 200
    assert any(item["action"] == "ledger.entry.created" for item in response.json()["items"])


def test_retry_backoff_is_deterministic():
    assert exponential_backoff_seconds(1) == 2
    assert exponential_backoff_seconds(3) == 8
    assert exponential_backoff_seconds(20) == 300
