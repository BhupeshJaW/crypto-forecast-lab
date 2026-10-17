export type Freshness = "fresh" | "aging" | "stale" | "unknown";

/**
 * Classifies data age against the backend's own limit (config.MAX_DATA_AGE_HOURS for candles and signals,
 * HEALTH_MAX_AGE_HOURS for the worker). Hourly candles are up to ~1 h old by design, so "fresh" is half
 * the limit and "stale" is anything over it, matching the point where the backend itself refuses to trade.
 */
export function freshness(ageHours: number | null | undefined, maxHours: number): Freshness {
  if (typeof ageHours !== "number" || !Number.isFinite(ageHours)) return "unknown";
  if (ageHours > maxHours) return "stale";
  if (ageHours > maxHours / 2) return "aging";
  return "fresh";
}

/** Age in hours of an ISO timestamp as seen from `nowMs`; null when unparseable. */
export function ageHoursFrom(iso: string | null | undefined, nowMs: number = Date.now()): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? (nowMs - t) / 3_600_000 : null;
}

/** A signal is only actionable until expires_at. */
export function isExpired(expiresAtIso: string | null | undefined, nowMs: number = Date.now()): boolean {
  if (!expiresAtIso) return false;
  const t = Date.parse(expiresAtIso);
  return Number.isFinite(t) && t <= nowMs;
}

/** The backend reports an age at fetch time; add the time passed in the browser since then. */
export function liveAge(ageAtFetchHours: number | null | undefined, fetchedAtMs: number, nowMs: number = Date.now()): number | null {
  if (typeof ageAtFetchHours !== "number" || !Number.isFinite(ageAtFetchHours)) return null;
  return ageAtFetchHours + Math.max(0, nowMs - fetchedAtMs) / 3_600_000;
}
