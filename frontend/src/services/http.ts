import { ApiError, errorFromResponse } from "./errors";

export interface ClientOptions {
  /** "" = same origin (dev proxy). Otherwise an absolute http(s) URL. */
  baseUrl: string;
  getToken: () => string | null;
  /** Called when the backend answers 401, so the UI can ask for a (new) token. */
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

export interface GetOptions {
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
  /** false for /health, which the backend leaves open. The token is then never sent. */
  auth?: boolean;
}

/** Accepts "" or an absolute http(s) URL; trims trailing slashes. Rejects anything else (e.g. javascript:). */
export function normalizeBaseUrl(raw: string | undefined): string {
  const v = (raw ?? "").trim();
  if (v === "") return "";
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    throw new Error(`VITE_API_BASE_URL must be empty or an absolute http(s) URL, got "${v}"`);
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    throw new Error(`VITE_API_BASE_URL must use http or https, got "${u.protocol}"`);
  }
  return v.replace(/\/+$/, "");
}

export function buildUrl(baseUrl: string, path: string, query?: GetOptions["query"]): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined) qs.set(k, String(v));
  const s = qs.toString();
  return `${baseUrl}${path}${s ? `?${s}` : ""}`;
}

export function createClient(opts: ClientOptions) {
  const timeoutMs = opts.timeoutMs ?? 15_000;

  async function get<T>(path: string, o: GetOptions = {}): Promise<T> {
    const doFetch = opts.fetchImpl ?? fetch;
    const headers: Record<string, string> = { Accept: "application/json" };
    const token = o.auth === false ? null : opts.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const ctrl = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      ctrl.abort();
    }, timeoutMs);
    const onOuterAbort = () => ctrl.abort();
    if (o.signal) {
      if (o.signal.aborted) ctrl.abort();
      else o.signal.addEventListener("abort", onOuterAbort, { once: true });
    }

    try {
      let res: Response;
      try {
        res = await doFetch(buildUrl(opts.baseUrl, path, o.query), { method: "GET", headers, signal: ctrl.signal });
      } catch {
        if (timedOut) throw new ApiError("timeout", `The backend did not answer within ${Math.round(timeoutMs / 1000)}s.`);
        if (o.signal?.aborted) throw new ApiError("aborted", "Request cancelled.");
        throw new ApiError("network", "Cannot reach the backend. Is the API running, and is the address correct?");
      }

      if (!res.ok) {
        let body: unknown = null;
        try {
          body = await res.json();
        } catch {
          /* non-JSON error body: ignore it, never display it */
        }
        const err = errorFromResponse(res.status, body, res.headers.get("Retry-After"));
        if (err.kind === "unauthorized") opts.onUnauthorized?.();
        throw err;
      }

      try {
        return (await res.json()) as T;
      } catch {
        throw new ApiError("invalid_response", "The backend returned a response that is not valid JSON.", res.status);
      }
    } finally {
      clearTimeout(timer);
      o.signal?.removeEventListener("abort", onOuterAbort);
    }
  }

  return { get };
}

export type HttpClient = ReturnType<typeof createClient>;
