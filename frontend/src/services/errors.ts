export type ApiErrorKind =
  | "network" // server unreachable / DNS / CORS block
  | "timeout"
  | "aborted"
  | "unauthorized" // 401
  | "forbidden" // 403
  | "not_found" // 404
  | "rate_limited" // 429
  | "bad_request" // 400 / 422
  | "upstream" // 502: the backend could not reach its data source
  | "server" // other 5xx
  | "invalid_response"; // 2xx but not JSON

/** Every message here is safe to show on screen: it never contains the token or raw response bodies. */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly retryAfterSec: number | null;
  constructor(kind: ApiErrorKind, message: string, status: number | null = null, retryAfterSec: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.retryAfterSec = retryAfterSec;
  }
}

export const isApiError = (e: unknown): e is ApiError => e instanceof ApiError;
export const isAbort = (e: unknown): boolean => isApiError(e) && e.kind === "aborted";

const DEFAULT_RETRY_SEC = 60;

/** Retry-After is either delta-seconds or an HTTP date. Falls back to 60 s (the backend's rate-limit window). */
export function parseRetryAfter(value: string | null, nowMs: number = Date.now()): number {
  if (!value) return DEFAULT_RETRY_SEC;
  const secs = Number(value);
  if (Number.isFinite(secs) && secs >= 0) return Math.min(Math.ceil(secs), 3600);
  const at = Date.parse(value);
  if (Number.isFinite(at)) return Math.min(Math.max(Math.ceil((at - nowMs) / 1000), 0), 3600);
  return DEFAULT_RETRY_SEC;
}

/** FastAPI sends {"detail": "text"} for our own errors and {"detail": [...]} for validation errors. */
function detailText(body: unknown): string | null {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string" && d.length > 0) return d.slice(0, 200);
  }
  return null;
}

export function errorFromResponse(status: number, body: unknown, retryAfterHeader: string | null): ApiError {
  const detail = detailText(body);
  if (status === 401) return new ApiError("unauthorized", "Authentication required, or the API token was rejected.", status);
  if (status === 403) return new ApiError("forbidden", "Access to this resource is forbidden.", status);
  if (status === 404) return new ApiError("not_found", detail ?? "Not found.", status);
  if (status === 429) {
    const sec = parseRetryAfter(retryAfterHeader);
    return new ApiError("rate_limited", `Rate limit reached. Retrying in about ${sec}s.`, status, sec);
  }
  if (status === 400 || status === 422) return new ApiError("bad_request", detail ?? "The request was rejected as invalid.", status);
  if (status === 502) return new ApiError("upstream", detail ?? "The backend could not reach its market-data source.", status);
  if (status >= 500) return new ApiError("server", detail ?? `The backend reported an internal error (HTTP ${status}).`, status);
  return new ApiError("server", `Unexpected response (HTTP ${status}).`, status);
}
