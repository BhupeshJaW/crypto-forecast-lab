import type { ApiError } from "../services/errors";

const TITLES: Record<ApiError["kind"], string> = {
  network: "Backend unreachable",
  timeout: "Backend timed out",
  aborted: "Request cancelled",
  unauthorized: "API token needed",
  forbidden: "Access forbidden",
  not_found: "Not found",
  rate_limited: "Rate limit reached",
  bad_request: "Request rejected",
  upstream: "Market-data source unavailable",
  server: "Backend error",
  invalid_response: "Unreadable response",
};

const HINTS: Partial<Record<ApiError["kind"], string>> = {
  network: "Start the API with: uvicorn api:app --host 127.0.0.1 --port 8000",
  unauthorized: "Use the Token button in the header. The token is whatever API_TOKEN is set to in the backend .env.",
  rate_limited: "Polling slows down automatically. Reduce open tabs if this repeats.",
  upstream: "The backend could not fetch candles from Binance. The last good data, if any, is still shown.",
};

export function ErrorState({ error, onRetry, showingStale = false }: { error: ApiError; onRetry?: () => void; showingStale?: boolean }) {
  const hint = HINTS[error.kind];
  return (
    <div role="alert" className="rounded border border-down/40 bg-down/10 px-4 py-3">
      <p className="text-sm font-medium text-down">{TITLES[error.kind]}</p>
      <p className="mt-1 text-sm text-fog-300">{error.message}</p>
      {hint ? <p className="mt-1 text-xs text-fog-500">{hint}</p> : null}
      {showingStale ? <p className="mt-1 text-xs text-warn">Showing the last data received. It may be out of date.</p> : null}
      {onRetry && error.kind !== "unauthorized" && error.kind !== "forbidden" ? (
        <button type="button" onClick={onRetry} className="mt-2 rounded border border-ink-600 px-2.5 py-1 text-xs text-fog-100 hover:bg-ink-700">
          Retry now
        </button>
      ) : null}
    </div>
  );
}
