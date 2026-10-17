import { useMemo, useState } from "react";
import { CandleChart, type Layers, type PriceLevels } from "../charts/CandleChart";
import { FreshnessBadge } from "../components/FreshnessBadge";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { GradeBadge } from "../components/Badges";
import { Panel, Stat } from "../components/Panel";
import { Skeleton } from "../components/Skeleton";
import { SignalDetail } from "../components/SignalDetail";
import { SourceBadge } from "../components/SourceBadge";
import { Warning } from "../components/Warning";
import { useApi } from "../hooks/useApi";
import { fmtFraction, fmtPct, fmtPrice, fmtUtc, tone } from "../lib/format";
import { liveAge } from "../lib/freshness";
import { prepareCandles } from "../lib/chartData";
import { isForecastAvailable, isModelAvailable, isSignalPresent } from "../lib/guards";
import { baseAsset } from "../lib/market";
import { hrefFor } from "../lib/route";
import { api } from "../services/api";

// The backend serves one interval only (1 h closed candles). "Range" is how many of them to load.
const RANGES = [{ n: 100, label: "100 h (~4 d)" }, { n: 300, label: "300 h (~12 d)" }, { n: 1000, label: "1000 h (~42 d)" }];

function CoinPicker({ active }: { active: string | null }) {
  const forecasts = useApi((s) => api.forecasts({ signal: s }));
  if (forecasts.error) return <ErrorState error={forecasts.error} onRetry={forecasts.refresh} />;
  if (forecasts.loading) return <Skeleton lines={1} />;
  return (
    <nav aria-label="Coins" className="flex flex-wrap gap-2">
      {forecasts.data?.map((f) => (
        <a key={f.symbol} href={hrefFor({ page: "coin", symbol: f.symbol })} aria-current={f.symbol === active ? "page" : undefined}
           className={`rounded border px-3 py-1.5 text-sm ${f.symbol === active ? "border-brass-500 bg-ink-700" : "border-ink-600 hover:bg-ink-800"}`}>
          {baseAsset(f.symbol)}
        </a>
      ))}
    </nav>
  );
}

export function CoinPage({ symbol }: { symbol: string | null }) {
  const [limit, setLimit] = useState(300);
  const [layers, setLayers] = useState<Layers>({ sma: true, bands: false, volume: true, rsi: true, macd: false });
  const enabled = symbol !== null;
  const analysis = useApi((s) => api.coin(symbol as string, { signal: s }), { pollMs: 60_000, enabled, key: symbol ?? "" });
  const candles = useApi((s) => api.candles(symbol as string, limit, { signal: s }), { pollMs: 120_000, enabled, key: `${symbol}:${limit}` });

  const prepared = useMemo(() => (candles.data ? prepareCandles(candles.data.candles) : null), [candles.data]);
  const signal = analysis.data?.signal;
  const levels = useMemo<PriceLevels | undefined>(() => {
    if (!isSignalPresent(signal) || signal.signal !== "BUY") return undefined;
    return { entryLow: signal.entry_zone?.[0], entryHigh: signal.entry_zone?.[1], stop: signal.stop_loss, target: signal.take_profit };
  }, [signal]);

  if (!symbol) {
    return <div className="space-y-4"><CoinPicker active={null} /><EmptyState title="Choose a coin" /></div>;
  }
  const f = analysis.data?.forecast;
  const m = analysis.data?.model;
  const c = candles.data;
  const age = c ? liveAge(c.data_age_hours, candles.fetchedAt ?? Date.now()) : null;

  return (
    <div className="space-y-4">
      <CoinPicker active={symbol} />

      <Panel
        title={`${baseAsset(symbol)}/USDT hourly candles`}
        aside={c ? <SourceBadge source={c.source} /> : null}
      >
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="text-xs text-fog-500">Range{" "}
            <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="ml-1 rounded border border-ink-600 bg-ink-950 px-2 py-1 text-sm text-fog-100">
              {RANGES.map((r) => <option key={r.n} value={r.n}>{r.label}</option>)}
            </select>
          </label>
          <span className="text-xs text-fog-500">Interval: 1 h only (the backend provides no other timeframes).</span>
          {(["sma", "bands", "volume", "rsi", "macd"] as const).map((k) => (
            <label key={k} className="flex items-center gap-1.5 text-xs text-fog-300">
              <input type="checkbox" checked={layers[k]} onChange={(e) => setLayers({ ...layers, [k]: e.target.checked })} />
              {{ sma: "SMA 20/50", bands: "Bollinger", volume: "Volume", rsi: "RSI", macd: "MACD" }[k]}
            </label>
          ))}
        </div>

        {candles.error ? <ErrorState error={candles.error} onRetry={candles.refresh} showingStale={!!c} /> : null}
        {candles.loading ? <Skeleton lines={6} /> : null}
        {c ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <FreshnessBadge ageHours={age} maxHours={3} label="Last closed candle" />
              <span className="text-xs text-fog-500">Candle opened {fmtUtc(c.last_candle_time)}; fetched {fmtUtc(c.fetched_at)}. Regime: <span className="text-fog-300">{c.regime}</span> (a description, not a forecast).</span>
            </div>
            {c.source !== "binance" ? <Warning title="Fallback data source">Candles came from {c.source} with no volume. Forecasts are not valid on this data.</Warning> : null}
            {prepared && prepared.dropped > 0 ? <Warning title={`${prepared.dropped} candle(s) could not be drawn`}>They contained missing or inconsistent prices.</Warning> : null}
            {prepared && prepared.ohlc.length === 0 ? <EmptyState title="No drawable candles returned" /> : null}
            {prepared && prepared.ohlc.length > 0 ? <CandleChart data={prepared} levels={levels} layers={layers} /> : null}
            <p className="text-xs text-fog-500">{c.note}</p>
          </div>
        ) : null}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Forecast" className="lg:col-span-1">
          {analysis.error ? <ErrorState error={analysis.error} onRetry={analysis.refresh} showingStale={!!analysis.data} /> : null}
          {analysis.loading ? <Skeleton lines={3} /> : null}
          {isForecastAvailable(f) ? (
            <div className="space-y-3">
              <dl className="grid grid-cols-2 gap-4">
                <Stat label="Predicted return" value={fmtPct(f.predicted_return_pct, 3)} tone={tone(f.predicted_return_pct)} />
                <Stat label="Horizon" value="1 hour" hint={`Target ${fmtUtc(f.target_time)}`} />
                <Stat label="Reference price" value={fmtPrice(f.reference_price)} />
                <Stat label="Predicted price" value={fmtPrice(f.predicted_price)} />
              </dl>
              <SourceBadge source={f.price_source} />
              <p className="text-xs text-fog-500">Made {fmtUtc(f.created_at)} by {f.model} ({f.model_version}). The uncertainty band is shown with the signal.</p>
            </div>
          ) : analysis.data ? <EmptyState title="No forecast yet" /> : null}
          {isModelAvailable(m) ? (
            <div className="mt-4 space-y-2 border-t border-ink-700 pt-3">
              <GradeBadge grade={m.grade} />
              <p className="text-xs text-fog-500">
                Direction right {fmtFraction(m.direction_accuracy)} on {m.unseen_hours_scored ?? "n/a"} unseen hours ({m.score_basis}). Live: {m.live_accuracy.verdict} ({m.live_accuracy.checked_predictions} checked).
              </p>
            </div>
          ) : null}
        </Panel>

        <Panel title="Signal" className="lg:col-span-2">
          {analysis.loading ? <Skeleton lines={4} /> : <SignalDetail signal={signal} />}
        </Panel>
      </div>
      {analysis.data ? <p className="text-xs text-fog-500">{analysis.data.disclaimer}</p> : null}
    </div>
  );
}
