import type { components } from "./generated/schema";
import { backoffDelayMs, defaultRetryOptions, shouldRetry, sleep, type RetryOptions } from "./retry";

export type LedgerEntryCreate = components["schemas"]["LedgerEntryCreate"];
export type LedgerEntryPage = components["schemas"]["LedgerEntryPage"];
export type WebhookEventCreate = components["schemas"]["WebhookEventCreate"];
export type WebhookEventRead = components["schemas"]["WebhookEventRead"];
export type WebhookReplayRequest = components["schemas"]["WebhookReplayRequest"];
export type WebhookReplayResult = components["schemas"]["WebhookReplayResult"];
export type SLODashboard = components["schemas"]["SLODashboard"];
export type SchemaVersionInfo = components["schemas"]["SchemaVersionInfo"];
export type ErrorResponse = components["schemas"]["ErrorResponse"];

export interface ApiToolkitClientOptions {
  baseUrl: string;
  apiKey: string;
  schemaVersion?: string;
  fetchImpl?: typeof fetch;
  retry?: Partial<RetryOptions>;
}

export class ApiToolkitError extends Error {
  readonly status: number;
  readonly response: ErrorResponse | unknown;

  constructor(status: number, response: ErrorResponse | unknown) {
    super(`API request failed with status ${status}`);
    this.status = status;
    this.response = response;
  }
}

export class ApiToolkitClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly schemaVersion?: string;
  private readonly fetchImpl: typeof fetch;
  private readonly retry: RetryOptions;

  constructor(options: ApiToolkitClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.schemaVersion = options.schemaVersion;
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.retry = { ...defaultRetryOptions, ...options.retry };
  }

  async listLedgerEntries(params: {
    page?: number;
    page_size?: number;
    account_id?: string;
    kind?: "debit" | "credit";
  } = {}): Promise<LedgerEntryPage> {
    return this.request("GET", "/v1/ledger/entries", { query: params });
  }

  async createLedgerEntry(payload: LedgerEntryCreate, idempotencyKey: string): Promise<components["schemas"]["LedgerEntryRead"]> {
    return this.request("POST", "/v1/ledger/entries", {
      body: payload,
      idempotencyKey
    });
  }

  async ingestWebhookEvent(payload: WebhookEventCreate, idempotencyKey: string): Promise<WebhookEventRead> {
    return this.request("POST", "/v1/webhooks/events", {
      body: payload,
      idempotencyKey
    });
  }

  async replayFailedEvent(eventId: string): Promise<WebhookEventRead> {
    return this.request("POST", `/v1/webhooks/events/${eventId}/replay`);
  }

  async replayFailedEvents(payload: WebhookReplayRequest): Promise<WebhookReplayResult> {
    return this.request("POST", "/v1/webhooks/replays", { body: payload });
  }

  async getSloDashboard(): Promise<SLODashboard> {
    return this.request("GET", "/v1/ops/slo-dashboard");
  }

  async getSchemaVersions(): Promise<SchemaVersionInfo> {
    return this.request("GET", "/v1/schemas/versions");
  }

  private async request<T>(
    method: string,
    path: string,
    options: {
      body?: unknown;
      query?: Record<string, string | number | undefined>;
      idempotencyKey?: string;
    } = {}
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }

    const headers: Record<string, string> = {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-API-Key": this.apiKey
    };
    if (this.schemaVersion) {
      headers["X-Schema-Version"] = this.schemaVersion;
    }
    if (options.idempotencyKey) {
      headers["X-Idempotency-Key"] = options.idempotencyKey;
    }

    let lastResponse: Response | undefined;
    for (let attempt = 1; attempt <= this.retry.attempts; attempt += 1) {
      const response = await this.fetchImpl(url, {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body)
      });
      lastResponse = response;

      if (response.ok) {
        return response.json() as Promise<T>;
      }
      if (attempt < this.retry.attempts && shouldRetry(response.status, this.retry)) {
        await sleep(backoffDelayMs(attempt, this.retry.baseDelayMs, this.retry.maxDelayMs));
        continue;
      }
      break;
    }

    const errorBody = await parseError(lastResponse);
    throw new ApiToolkitError(lastResponse?.status ?? 0, errorBody);
  }
}

async function parseError(response: Response | undefined): Promise<unknown> {
  if (!response) {
    return { code: "NETWORK_ERROR", message: "No response was received." };
  }
  try {
    return await response.json();
  } catch {
    return { code: "UNPARSEABLE_ERROR", message: await response.text() };
  }
}
