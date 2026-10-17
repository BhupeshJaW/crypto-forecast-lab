import { useState } from "react";
import { useAuth } from "../hooks/useAuth";

/** Asks for the backend API token. Shown automatically after a 401, or from the header button. */
export function TokenGate({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { store, token, rejected } = useAuth();
  const [value, setValue] = useState("");
  const [remember, setRemember] = useState(false);
  if (!open && !rejected) return null;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="token-title" className="fixed inset-0 z-20 flex items-start justify-center bg-ink-950/80 p-4 pt-24">
      <form
        className="w-full max-w-md rounded-md border border-ink-600 bg-ink-900 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          store.setToken(value, remember);
          setValue("");
          onClose();
        }}
      >
        <h2 id="token-title" className="text-base font-semibold">API token</h2>
        <p className="mt-1 text-sm text-fog-300">
          {rejected ? "The backend rejected the request. Enter the correct token." : "Enter the token the backend expects in API_TOKEN."}
        </p>
        <label className="mt-4 block text-xs text-fog-500" htmlFor="api-token">Bearer token</label>
        <input
          id="api-token" type="password" autoComplete="off" spellCheck={false} autoFocus value={value}
          onChange={(e) => setValue(e.target.value)}
          className="mt-1 w-full rounded border border-ink-600 bg-ink-950 px-3 py-2 text-sm"
        />
        <label className="mt-3 flex items-center gap-2 text-sm text-fog-300">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Remember in this browser tab only
        </label>
        <p className="mt-2 text-xs text-fog-500">Kept in memory, sent only to the API as a bearer header, never stored permanently or put in the page code.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="submit" disabled={!value.trim()} className="rounded bg-brass-500 px-3 py-1.5 text-sm font-medium text-ink-950 disabled:opacity-40">
            Use token
          </button>
          {token ? (
            <button type="button" onClick={() => { store.clear(); onClose(); }} className="rounded border border-ink-600 px-3 py-1.5 text-sm hover:bg-ink-700">
              Forget token
            </button>
          ) : null}
          <button type="button" onClick={onClose} className="rounded px-3 py-1.5 text-sm text-fog-300 hover:bg-ink-700">Cancel</button>
        </div>
      </form>
    </div>
  );
}
