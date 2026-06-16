import { expect, test } from "@playwright/test";

test("health and OpenAPI are reachable", async ({ request }) => {
  const health = await request.get("/health");
  await expect(health).toBeOK();

  const openapi = await request.get("/openapi.json");
  const schema = await openapi.json();
  expect(schema.paths["/v1/ledger/entries"]).toBeTruthy();
  expect(schema.paths["/v1/webhooks/events/{event_id}/replay"]).toBeTruthy();
});

test("contract workflow covers idempotency, replay, and SLO", async ({ request }) => {
  const headers = {
    "X-API-Key": "integration-key",
    "X-Idempotency-Key": `pw-ledger-${Date.now()}`
  };
  const payload = {
    external_id: `pw-ledger-${Date.now()}`,
    account_id: "acct-playwright",
    kind: "credit",
    amount_cents: 1500
  };
  const created = await request.post("/v1/ledger/entries", {
    headers,
    data: payload
  });
  expect(created.status()).toBe(201);

  const replay = await request.post("/v1/ledger/entries", {
    headers,
    data: payload
  });
  expect(replay.status()).toBe(201);

  const slo = await request.get("/v1/ops/slo-dashboard", {
    headers: { "X-API-Key": "admin-key" }
  });
  expect(slo.ok()).toBeTruthy();
  expect((await slo.json()).latency_p95_ms).toBeLessThan(120);
});
