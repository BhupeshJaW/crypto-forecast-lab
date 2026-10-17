import { useCallback, useEffect, useRef, useState } from "react";
import { nextDelay } from "../lib/polling";
import { ApiError, isAbort, isApiError } from "../services/errors";
import { useAuth } from "./useAuth";

export interface UseApiOptions {
  /** Poll interval in ms. Omit for a single fetch. Pauses while the tab is hidden. */
  pollMs?: number;
  enabled?: boolean;
  /** Change this to refetch for different arguments (e.g. the selected symbol). Old data is cleared. */
  key?: string;
}

export interface ApiState<T> {
  /** Last successful response. Kept (and flagged via `error`) when a later poll fails, so the screen never goes blank. */
  data: T | null;
  error: ApiError | null;
  /** True only for the first load with nothing to show yet. */
  loading: boolean;
  refreshing: boolean;
  /** Browser time of the last successful fetch (ms), for "updated x ago" and live-age maths. */
  fetchedAt: number | null;
  refresh: () => void;
}

export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>, opts: UseApiOptions = {}): ApiState<T> {
  const { pollMs, enabled = true, key = "" } = opts;
  const { version } = useAuth(); // refetch when the token changes
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const [s, setS] = useState<Omit<ApiState<T>, "refresh">>({
    data: null, error: null, loading: enabled, refreshing: false, fetchedAt: null,
  });
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((t) => t + 1), []);
  const lastKey = useRef(key);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let ctrl: AbortController | undefined;
    let failures = 0;

    if (lastKey.current !== key) {
      lastKey.current = key;
      setS({ data: null, error: null, loading: true, refreshing: false, fetchedAt: null });
    }

    const schedule = (err: ApiError | null) => {
      if (!pollMs || cancelled) return;
      const d = nextDelay(pollMs, err, failures);
      if (d !== null) timer = setTimeout(run, d);
    };

    async function run() {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.hidden) {
        if (pollMs) timer = setTimeout(run, pollMs); // skip while hidden; the visibility listener refetches on return
        return;
      }
      ctrl = new AbortController();
      setS((p) => ({ ...p, refreshing: true }));
      try {
        const data = await fetcherRef.current(ctrl.signal);
        if (cancelled) return;
        failures = 0;
        setS({ data, error: null, loading: false, refreshing: false, fetchedAt: Date.now() });
        schedule(null);
      } catch (e) {
        if (cancelled || isAbort(e)) return;
        const err = isApiError(e) ? e : new ApiError("server", "Unexpected error.");
        failures += 1;
        setS((p) => ({ ...p, error: err, loading: false, refreshing: false }));
        schedule(err);
      }
    }

    const onVisible = () => {
      if (document.hidden || cancelled) return;
      if (timer) clearTimeout(timer);
      void run();
    };
    document.addEventListener("visibilitychange", onVisible);
    void run();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      ctrl?.abort();
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, pollMs, key, version, tick]);

  return { ...s, refresh };
}
