export interface RetryOptions {
  attempts: number;
  baseDelayMs: number;
  maxDelayMs: number;
  retryStatuses: number[];
}

export const defaultRetryOptions: RetryOptions = {
  attempts: 3,
  baseDelayMs: 100,
  maxDelayMs: 2_000,
  retryStatuses: [408, 425, 429, 500, 502, 503, 504]
};

export function backoffDelayMs(
  attempt: number,
  baseDelayMs = defaultRetryOptions.baseDelayMs,
  maxDelayMs = defaultRetryOptions.maxDelayMs
): number {
  return Math.min(maxDelayMs, baseDelayMs * 2 ** Math.max(0, attempt - 1));
}

export function shouldRetry(status: number, options = defaultRetryOptions): boolean {
  return options.retryStatuses.includes(status);
}

export async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}
