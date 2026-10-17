import { useMemo } from "react";
import { FreshnessBadge } from "../components/FreshnessBadge";
import { GradeBadge, SignalBadge } from "../components/Badges";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Panel, Stat } from "../components/Panel";
import { Skeleton } from "../components/Skeleton";
import { SourceBadge } from "../components/SourceBadge";
import { Warning } from "../components/Warning";
import { useApi } from "../hooks/useApi";
import { fmtPct, fmtPrice, fmtUtc, tone } from "../lib/format";
import { ageHoursFrom, isExpired } from "../lib/freshness";
import { bySymbol, isForecastAvailable, isModelAvailable, isSignalPresent } from "../lib/guards";
import { parseAlertLines } from "../lib/alertLog";
import { changePct, baseAsset } from "../lib/market";
import { totalPnl } from "../lib/portfolio";
import { hrefFor } from "../lib/route";
import { api } from "../services/api";
import type { Forecast, ModelPerformance, Signal } from "../types/api";

function CoinCard({ symbol, forecast, signal, model, maxAge }: { symbol: string; forecast?: Forecast; signal?: Signal; model?: ModelPerformance; maxAge: number }) {
  const candles = useApi((signal) => api.candles(symbol, 50, { signal }), { pollMs: 300_000, key: symbol });
  const closes = candles.data?.candles.map((c) => c.close);
  const change = closes ? changePct(closes, 24) : null;
  const f = isForecastAvailable(forecast) ? forecast : null;
  const sig = isSignalPresent(signal) ? signal : null;
  const m = isModelAvailable(model) ? model : null;

  return (
    <article className="rounded-md border border-ink-700 bg-ink-900 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <a href={hrefFor({ page: "coin", symbol })} className="text-base font-semibold hover:text-brass-400">{baseAsset(symbol)}<span className="text-fog-500">/USDT</span></a>
          <p className="mt-0.5"><SourceBadge source={f?.price_source ?? candles.data?.source} /></p>
        </div>
        <SignalBadge kind={sig?.signal ?? null} expired={sig ? isExpired(sig.expires_at) : false} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3">
        <Stat label="Reference price" value={fmtPrice(f?.reference_price ?? null)} />
        <Stat label="24 h change" value={candles.loading ? "..." : fmtPct(change)} tone={tone(change)} hint={candles.error ? "Candles unavailable" : "From 1 h closed candles"} />
        <Stat label="Forecast, next hour" value={fmtPct(f?.predicted_return_pct ?? null, 3)} tone={tone(f?.predicted_return_pct)} hint={f ? `For ${fmtUtc(f.target_time)}` : "No forecast yet"} />
        <Stat label="Model" value={m ? m.model : "n/a"} hint={m ? undefined : "Not trained yet"} />
      </dl>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {m ? <GradeBadge grade={m.grade} /> : null}
        {f ? <FreshnessBadge ageHours={ageHoursFrom(f.created_at)} maxHours={maxAge} label="Forecast made" /> : null}
      </div>
      {sig && sig.blockers.length > 0 ? <p className="mt-2 text-xs text-warn">{sig.blockers[0]}</p> : null}
    </article>
  );
}

export function OverviewPage() {
  const forecasts = useApi((s) => api.forecasts({ signal: s }), { pollMs: 60_000 });
  const signals = useApi((s) => api.signals({ signal: s }), { pollMs: 60_000 });
  const models = useApi((s) => api.models({ signal: s }), { pollMs: 300_000 });
  const portfolio = useApi((s) => api.paperPortfolio({ signal: s }), { pollMs: 60_000 });
  const alerts = useApi((s) => api.recentAlerts(50, { signal: s }), { pollMs: 120_000 });
  const health = useApi((s) => api.health({ signal: s }), { pollMs: 30_000 });

  const maxAge = health.data?.max_age_hours ?? 3;
  const symbols = forecasts.data?.map((f) => f.symbol) ?? [];
  const recent = useMemo(() => parseAlertLines(alerts.data ?? []).slice(0, 5), [alerts.data]);
  const allLow = models.data && models.data.length > 0 && models.data.every((m) => !isModelAvailable(m) || m.grade === "low");
  const pf = portfolio.data;
  const pnl = pf ? totalPnl(pf) : null;
  const unit = pf?.currency.split(" ")[0] ?? "USDT";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
        {health.data ? <FreshnessBadge ageHours={health.data.worker_age_hours} maxHours={health.data.max_age_hours} label="Worker last ran" /> : health.error ? <span className="text-xs text-down">Backend status unavailable</span> : null}
        <span className="text-xs text-fog-500">Prices are Binance USDT references, not CoinSwitch INR quotes.</span>
      </div>

      {allLow ? (
        <Warning title="No model currently beats &quot;price stays the same&quot; on unseen data">
          Signals will mostly be HOLD or NO TRADE, and forecasts should not be used for decisions. This is the honest state of the models, not a bug.
        </Warning>
      ) : null}

      {forecasts.error ? <ErrorState error={forecasts.error} onRetry={forecasts.refresh} showingStale={!!forecasts.data} /> : null}
      {forecasts.loading ? <Skeleton lines={4} /> : null}
      {forecasts.data && forecasts.data.length === 0 ? <EmptyState title="No coins are tracked">Add symbols to SYMBOLS in the backend config.</EmptyState> : null}
      {forecasts.data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {symbols.map((s) => (
            <CoinCard key={s} symbol={s} forecast={bySymbol(forecasts.data, s)} signal={bySymbol(signals.data, s)} model={bySymbol(models.data, s)} maxAge={maxAge} />
          ))}
        </div>
      ) : null}
      {signals.error ? <ErrorState error={signals.error} onRetry={signals.refresh} showingStale={!!signals.data} /> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Paper portfolio" aside={<a className="text-xs text-brass-400 hover:underline" href={hrefFor({ page: "portfolio" })}>Details</a>}>
          {portfolio.error ? <ErrorState error={portfolio.error} onRetry={portfolio.refresh} showingStale={!!pf} /> : null}
          {portfolio.loading ? <Skeleton lines={2} /> : null}
          {pf ? (
            pf.equity === undefined || pf.equity === null ? <EmptyState title="No equity history yet">The worker records equity after its first cycle.</EmptyState> : (
              <dl className="grid grid-cols-2 gap-4">
                <Stat label={`Equity (${unit}, paper)`} value={fmtPrice(pf.equity, unit)} />
                <Stat label="P&L since start" value={pnl ? `${fmtPrice(pnl.abs, unit)} (${fmtPct(pnl.pct)})` : "n/a"} tone={tone(pnl?.abs)} />
                <Stat label="Closed trades" value={pf.trades} hint={pf.statistically_conclusive ? undefined : "Too few to judge"} />
                <Stat label="Max drawdown" value={fmtPct(pf.max_drawdown_pct, 2, false)} tone={tone(pf.max_drawdown_pct)} />
              </dl>
            )
          ) : null}
        </Panel>

        <Panel title="Recent alerts" aside={<a className="text-xs text-brass-400 hover:underline" href={hrefFor({ page: "alerts" })}>All</a>}>
          {alerts.error ? <ErrorState error={alerts.error} onRetry={alerts.refresh} showingStale={!!alerts.data} /> : null}
          {alerts.loading ? <Skeleton lines={3} /> : null}
          {alerts.data && recent.length === 0 ? <EmptyState title="No alerts or errors logged" /> : null}
          <ul className="space-y-2">
            {recent.map((a, i) => (
              <li key={i} className="text-sm">
                <span className={`mr-2 text-xs ${a.level === "ERROR" ? "text-down" : "text-fog-500"}`}>{a.loggedAt ?? "no timestamp"}</span>
                <span className="text-fog-300">{a.message}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <p className="text-xs text-fog-500">Forecasts and signals refresh every minute; candles every five.</p>
    </div>
  );
}
