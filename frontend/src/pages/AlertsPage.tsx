import { useMemo, useState } from "react";
import { SignalBadge } from "../components/Badges";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Panel, Stat } from "../components/Panel";
import { Skeleton } from "../components/Skeleton";
import { Table, Td } from "../components/Table";
import { useApi } from "../hooks/useApi";
import { parseAlertLines, type AlertKind } from "../lib/alertLog";
import { fmtPct, fmtUtc } from "../lib/format";
import { isExpired } from "../lib/freshness";
import { isSignalPresent } from "../lib/guards";
import { api } from "../services/api";

const KINDS: { id: AlertKind | "all"; label: string }[] = [
  { id: "all", label: "All" }, { id: "alert", label: "Alerts sent" }, { id: "error", label: "Errors" }, { id: "fetch_failed", label: "Failed fetches" },
];

export function AlertsPage() {
  const cfg = useApi((s) => api.alertConfig({ signal: s }), { pollMs: 300_000 });
  const signals = useApi((s) => api.signals({ signal: s }), { pollMs: 60_000 });
  const log = useApi((s) => api.recentAlerts(200, { signal: s }), { pollMs: 120_000 });
  const [kind, setKind] = useState<AlertKind | "all">("all");
  const lines = useMemo(() => parseAlertLines(log.data ?? []), [log.data]);
  const shown = kind === "all" ? lines : lines.filter((l) => l.kind === kind);

  return (
    <div className="space-y-4">
      <Panel title="Latest signal per coin">
        {signals.error ? <ErrorState error={signals.error} onRetry={signals.refresh} showingStale={!!signals.data} /> : null}
        {signals.loading ? <Skeleton lines={3} /> : null}
        {signals.data ? (
          <Table caption="Latest signals" head={["Coin", "Signal", "Status", "Made", "Expires", "Forecast", "Net edge"]}>
            {signals.data.map((s) => isSignalPresent(s) ? (
              <tr key={s.symbol}>
                <Td>{s.symbol}</Td><Td><SignalBadge kind={s.signal} expired={isExpired(s.expires_at)} /></Td>
                <Td>{isExpired(s.expires_at) ? "Expired" : s.blockers.length ? "Blocked" : "Active"}</Td>
                <Td>{fmtUtc(s.created_at)}</Td><Td>{fmtUtc(s.expires_at)}</Td>
                <Td>{fmtPct(s.predicted_return_pct, 3)}</Td><Td>{fmtPct(s.net_edge_after_costs_pct, 3)}</Td>
              </tr>
            ) : <tr key={s.symbol}><Td>{s.symbol}</Td><Td><SignalBadge kind={null} /></Td><Td className="text-fog-500" >Waiting for first worker cycle</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td></tr>)}
          </Table>
        ) : null}
        <p className="mt-2 text-xs text-fog-500">Telegram and email alerts are sent only for BUY and SELL-exit signals, once per signal. Expiry is one forecast horizon after the signal was made.</p>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Delivery channels" className="lg:col-span-1">
          {cfg.error ? <ErrorState error={cfg.error} onRetry={cfg.refresh} showingStale={!!cfg.data} /> : null}
          {cfg.loading ? <Skeleton lines={2} /> : null}
          {cfg.data ? (
            <dl className="space-y-3">
              <Stat label="Active channels" value={cfg.data.channels.length ? cfg.data.channels.join(", ") : "None configured"} hint={cfg.data.channels.length ? undefined : "Set Telegram or email values in the backend .env."} />
              <Stat label="Drawdown alert" value={`${cfg.data.drawdown_alert_pct}% below peak`} />
            </dl>
          ) : null}
        </Panel>

        <Panel title="Recent log events" className="lg:col-span-2">
          <div role="group" aria-label="Filter log events" className="mb-3 flex flex-wrap gap-2">
            {KINDS.map((k) => (
              <button key={k.id} type="button" aria-pressed={kind === k.id} onClick={() => setKind(k.id)}
                className={`rounded border px-2.5 py-1 text-xs ${kind === k.id ? "border-brass-500 bg-ink-700" : "border-ink-600 hover:bg-ink-800"}`}>{k.label}</button>
            ))}
          </div>
          {log.error ? <ErrorState error={log.error} onRetry={log.refresh} showingStale={!!log.data} /> : null}
          {log.loading ? <Skeleton lines={4} /> : null}
          {log.data && shown.length === 0 ? <EmptyState title="Nothing logged for this filter" /> : null}
          <ul className="max-h-96 divide-y divide-ink-800 overflow-y-auto">
            {shown.map((l, i) => (
              <li key={i} className="py-2 text-sm">
                <span className="mr-2 text-xs text-fog-500">{l.loggedAt ?? "no timestamp"}</span>
                <span className={`mr-2 text-xs ${l.level === "ERROR" ? "text-down" : l.level === "WARNING" ? "text-warn" : "text-fog-500"}`}>{l.level}</span>
                <span className="break-words text-fog-300">{l.message}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-fog-500">Log times are shown exactly as written by the backend, which does not record a time zone.</p>
        </Panel>
      </div>
    </div>
  );
}
