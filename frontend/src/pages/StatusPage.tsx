import { ErrorState } from "../components/ErrorState";
import { FreshnessBadge } from "../components/FreshnessBadge";
import { Panel, Stat } from "../components/Panel";
import { Skeleton } from "../components/Skeleton";
import { fmtUtc } from "../lib/format";
import { api } from "../services/api";
import { useApi } from "../hooks/useApi";

/** Foundation page: proves the open (/health) and authenticated (/api/alerts/config) paths end to end. Real data only. */
export function StatusPage() {
  const health = useApi((signal) => api.health({ signal }), { pollMs: 30_000 });
  const alerts = useApi((signal) => api.alertConfig({ signal }), { pollMs: 60_000 });
  const h = health.data;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel
        title="Backend and worker"
        aside={h ? <span className={`text-xs ${h.status === "ok" ? "text-up" : "text-warn"}`}>{h.status === "ok" ? "Healthy" : "Degraded"}</span> : null}
      >
        {health.error ? <ErrorState error={health.error} onRetry={health.refresh} showingStale={h !== null} /> : null}
        {health.loading ? <Skeleton /> : null}
        {h ? (
          <dl className="mt-1 grid grid-cols-2 gap-4">
            <Stat label="Last successful worker cycle" value={fmtUtc(h.worker_last_success)} />
            <Stat label="Worker age" value={<FreshnessBadge ageHours={h.worker_age_hours} maxHours={h.max_age_hours} label="Last cycle" />} />
            <Stat label="Tracked coins" value={h.tracked_coins} />
            <Stat label="CoinSwitch API keys" value={h.coinswitch_configured ? "Present" : "Not set"} hint="Not used for prices yet." />
          </dl>
        ) : null}
        {h && h.status !== "ok" ? (
          <p className="mt-3 text-sm text-warn">The worker has not completed a cycle within {h.max_age_hours} h. Forecasts and signals may be stale.</p>
        ) : null}
      </Panel>

      <Panel title="Alert channels">
        {alerts.error ? <ErrorState error={alerts.error} onRetry={alerts.refresh} showingStale={alerts.data !== null} /> : null}
        {alerts.loading ? <Skeleton lines={2} /> : null}
        {alerts.data ? (
          <dl className="grid grid-cols-2 gap-4">
            <Stat label="Active channels" value={alerts.data.channels.length ? alerts.data.channels.join(", ") : "None configured"} />
            <Stat label="Drawdown alert at" value={`${alerts.data.drawdown_alert_pct}% below peak`} />
            <div className="col-span-2 text-sm text-fog-300">{alerts.data.signal_alerts}</div>
          </dl>
        ) : null}
      </Panel>
    </div>
  );
}
