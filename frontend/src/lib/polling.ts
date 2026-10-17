import type { ApiErrorKind } from "../services/errors";

const MAX_BACKOFF_MS = 5 * 60_000;

/**
 * Delay before the next poll, or null to stop polling.
 *  - no error: the normal interval
 *  - 401/403: stop. Hammering a backend that rejects us only trips its rate limit; polling resumes when the token changes.
 *  - 429: wait at least as long as the server asked
 *  - anything else: exponential backoff, capped at 5 minutes
 */
export function nextDelay(
  baseMs: number,
  err: { kind: ApiErrorKind; retryAfterSec: number | null } | null,
  consecutiveFailures: number,
): number | null {
  if (!err) return baseMs;
  if (err.kind === "unauthorized" || err.kind === "forbidden") return null;
  if (err.kind === "rate_limited") return Math.max(baseMs, (err.retryAfterSec ?? 60) * 1000);
  return Math.min(baseMs * 2 ** Math.max(consecutiveFailures, 1), MAX_BACKOFF_MS);
}
