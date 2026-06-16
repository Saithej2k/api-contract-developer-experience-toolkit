import { ApiToolkitClient, ApiToolkitError } from "../../src/client";
import { backoffDelayMs } from "../../src/retry";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("ApiToolkitClient", () => {
  test("sends idempotency and schema version headers on ledger writes", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse({
        id: "ledger_1",
        external_id: "ext_1",
        account_id: "acct_1",
        kind: "credit",
        amount_cents: 500,
        currency: "USD",
        description: null,
        risk_score: 0,
        schema_version: "2025-02-01",
        metadata: {},
        created_at: "2026-01-01T00:00:00Z"
      }, 201)
    );
    const client = new ApiToolkitClient({
      baseUrl: "http://localhost:8000",
      apiKey: "integration-key",
      schemaVersion: "2025-02-01",
      fetchImpl
    });

    await client.createLedgerEntry(
      {
        external_id: "ext_1",
        account_id: "acct_1",
        kind: "credit",
        amount_cents: 500,
        currency: "USD",
        description: null,
        risk_score: 0,
        client_reference_id: null,
        metadata: {}
      },
      "idem-001"
    );

    const [, init] = fetchImpl.mock.calls[0];
    expect(init.headers["X-API-Key"]).toBe("integration-key");
    expect(init.headers["X-Idempotency-Key"]).toBe("idem-001");
    expect(init.headers["X-Schema-Version"]).toBe("2025-02-01");
  });

  test("retries transient failures with exponential backoff", async () => {
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce(jsonResponse({ code: "TEMPORARY" }, 503))
      .mockResolvedValueOnce(jsonResponse({ service: "toolkit", latency_p95_ms: 94 }, 200));
    const client = new ApiToolkitClient({
      baseUrl: "http://localhost:8000",
      apiKey: "admin-key",
      fetchImpl,
      retry: { attempts: 2, baseDelayMs: 1, maxDelayMs: 1 }
    });

    await expect(client.getSloDashboard()).resolves.toMatchObject({ latency_p95_ms: 94 });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  test("throws typed API errors", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse({
        code: "FORBIDDEN",
        message: "Role cannot perform action.",
        details: {},
        request_id: null
      }, 403)
    );
    const client = new ApiToolkitClient({
      baseUrl: "http://localhost:8000",
      apiKey: "analyst-key",
      fetchImpl,
      retry: { attempts: 1 }
    });

    await expect(client.getSchemaVersions()).rejects.toBeInstanceOf(ApiToolkitError);
  });

  test("backoff delay caps at max delay", () => {
    expect(backoffDelayMs(1, 100, 500)).toBe(100);
    expect(backoffDelayMs(4, 100, 500)).toBe(500);
  });
});
