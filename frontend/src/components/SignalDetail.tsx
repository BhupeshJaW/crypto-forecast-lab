import { fmtAge, fmtNumber, fmtPct, fmtPrice, fmtUtc, tone } from "../lib/format";
import { ageHoursFrom, isExpired } from "../lib/freshness";
import type { Signal } from "../types/api";
import { isSignalPresent } from "../lib/guards";
import { GradeBadge, SignalBadge } from "./Badges";
import { EmptyState } from "./EmptyState";
import { SourceBadge } from "./SourceBadge";
import { Stat } from "./Panel";
import { Warning } from "./Warning";

export function SignalDetail({ signal }: { signal: Signal | undefined }) {
  if (!isSignalPresent(signal)) {
    return <EmptyState title="No signal generated yet">{signal && "note" in signal ? signal.note : "The worker has not produced a signal for this coin."} Run <code>python scheduler.py --once</code> or wait for the next hourly cycle.</EmptyState>;
  }
  const s = signal;
  const expired = isExpired(s.expires_at);
  const sym = "USDT";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <SignalBadge kind={s.signal} expired={expired} />
        {s.sell_type === "bearish_not_held" ? <span className="text-xs text-fog-300">Bearish, but long-only spot: nothing held, so no sale.</span> : null}
        {s.sell_type === "exit_position" ? <span className="text-xs text-fog-300">Exit signal for an open paper position.</span> : null}
        <GradeBadge grade={s.model_grade} />
        <SourceBadge source={s.price_source} />
      </div>

      {expired ? <Warning title="This signal has expired">It was only valid for {s.horizon_hours} h after {fmtUtc(s.created_at)}. Do not act on it.</Warning> : null}
      {s.blockers.length > 0 ? (
        <Warning title="Blocked by a safety rule">
          <ul className="list-disc pl-5">{s.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
        </Warning>
      ) : null}

      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label={`Forecast (${s.horizon_hours} h)`} value={fmtPct(s.predicted_return_pct)} tone={tone(s.predicted_return_pct)} />
        <Stat label="Typical error band" value={s.typical_error_band_pct ? `${fmtPct(s.typical_error_band_pct[0])} to ${fmtPct(s.typical_error_band_pct[1])}` : "n/a"} hint="Typical miss size, not a confidence interval." />
        <Stat label="Est. round-trip cost" value={fmtPct(s.estimated_round_trip_cost_pct, 2, false)} />
        <Stat label="Net edge after costs" value={fmtPct(s.net_edge_after_costs_pct, 3)} tone={tone(s.net_edge_after_costs_pct)} />
      </dl>

      {s.signal === "BUY" && s.entry_zone && s.stop_loss !== undefined && s.take_profit !== undefined ? (
        <dl className="grid grid-cols-2 gap-4 rounded border border-ink-700 p-3 sm:grid-cols-4">
          <Stat label="Entry zone" value={`${fmtNumber(s.entry_zone[0])} to ${fmtNumber(s.entry_zone[1])}`} hint={sym} />
          <Stat label="Stop-loss" value={fmtPrice(s.stop_loss, sym)} tone="down" />
          <Stat label="Take-profit" value={fmtPrice(s.take_profit, sym)} tone="up" />
          <Stat label="Reward : risk" value={s.reward_to_risk !== undefined ? fmtNumber(s.reward_to_risk) : "n/a"} />
        </dl>
      ) : null}

      <div>
        <h3 className="text-sm font-medium">Why</h3>
        {s.reasons.length > 0 ? <ul className="mt-1 list-disc pl-5 text-sm text-fog-300">{s.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : <p className="mt-1 text-sm text-fog-500">No reasons recorded.</p>}
      </div>

      <p className="text-xs text-fog-500">
        Made {fmtUtc(s.created_at)} ({fmtAge(ageHoursFrom(s.created_at))}); valid until {fmtUtc(s.expires_at)}. Candle was {fmtAge(s.data_age_hours)} when the signal was made.
        {s.holdout_hours ? ` Model scored on ${s.holdout_hours} unseen hours.` : ""} {s.price_note}
      </p>
    </div>
  );
}
