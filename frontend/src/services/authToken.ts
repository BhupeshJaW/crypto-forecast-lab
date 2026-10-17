/**
 * Holds the API bearer token entered by the user. It lives in memory; "remember in this tab" additionally
 * keeps it in sessionStorage (cleared when the tab closes). It is never written to localStorage, never put
 * in a URL, never logged, and never part of the build.
 */
const KEY = "crypto_predictor_api_token";

export interface AuthState {
  token: string | null;
  /** True after the backend answered 401: the UI should ask for a token. */
  rejected: boolean;
  /** Increments whenever the token changes, so data hooks refetch. */
  version: number;
}

type Listener = () => void;
type KV = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function createAuthStore(storage: KV | null = null) {
  const read = (): string | null => {
    try {
      return storage?.getItem(KEY) ?? null;
    } catch {
      return null;
    }
  };
  const write = (v: string | null) => {
    try {
      if (v === null) storage?.removeItem(KEY);
      else storage?.setItem(KEY, v);
    } catch {
      /* storage blocked: stay in memory only */
    }
  };

  let state: AuthState = { token: read(), rejected: false, version: 0 };
  const listeners = new Set<Listener>();
  const emit = (next: AuthState) => {
    state = next;
    listeners.forEach((l) => l());
  };

  return {
    getState: () => state,
    getToken: () => state.token,
    subscribe(l: Listener) {
      listeners.add(l);
      return () => void listeners.delete(l);
    },
    setToken(token: string, remember: boolean) {
      const t = token.trim();
      if (!t) return;
      write(remember ? t : null);
      emit({ token: t, rejected: false, version: state.version + 1 });
    },
    clear() {
      write(null);
      emit({ token: null, rejected: false, version: state.version + 1 });
    },
    markRejected() {
      if (!state.rejected) emit({ ...state, rejected: true });
    },
  };
}

export type AuthStore = ReturnType<typeof createAuthStore>;

function browserSession(): KV | null {
  try {
    return typeof window !== "undefined" ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

export const authStore: AuthStore = createAuthStore(browserSession());
