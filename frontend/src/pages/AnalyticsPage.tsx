import { GradeBadge } from "../components/Badges";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Panel } from "../components/Panel";
import { Skeleton } from "../components/Skeleton";
import { Table, Td } from "../components/Table";
import { Warning } from "../components/Warning";
import { useApi } from "../hooks/useApi";
import { fmtFraction, fmtNumber, fmtPct, fmtUtc, tone } from "../lib/format";
import { isModelAvailable } from "../lib/guards";
import { api } from "../services/api";

const toneClass = (n: number | null | undefined) => (tone(n) === "up" ? "text-up" : tone(n) === "down" ? "text-down" : "");

export function AnalyticsPage() {
  const models = useApi((s) => api.models({ signal: s }), { pollMs: 300_000 });
  const backtest = useApi((s) => api.backtest({ signal: s }), { pollMs: 600_000 });
  const bt = backtest.data;
  const rows = bt && bt.available ? bt.rows : [];
  const anyInconclusive = rows.some((r) => r.inconclusive);

  return (
    <div className="space-y-4">
      <Panel title="Model performance">
        {models.error ? <ErrorState error={models.error} onRetry={models.refresh} showingStale={!!models.data} /> : null}
        {models.loading ? <Skeleton lines={3} /> : null}
        {models.data && models.data.length === 0 ? <EmptyState title="No models yet" /> : null}
        {models.data && models.data.length > 0 ? (
          <div className="space-y-3">
            <Table caption="Model scores per coin" head={["Coin", "Model", "Grade", "Skill vs naive", "Direction right", "MAE (return)", "Naive MAE", "Scored on", "Trained", "Live direction"]}>
              {models.data.map((m) => isModelAvailable(m) ? (
                <tr key={m.symbol}>
                  <Td>{m.symbol}</Td><Td>{m.model}</Td><Td><GradeBadge grade={m.grade} /></Td>
                  <Td className={toneClass(m.skill_vs_naive_pct)}>{fmtPct(m.skill_vs_naive_pct)}</Td>
                  <Td>{fmtFraction(m.direction_accuracy)}</Td>
                  <Td>{fmtPct(m.mae === null ? null : m.mae * 100, 3, false)}</Td>
                  <Td>{fmtPct(m.naive_mae === null ? null : m.naive_mae * 100, 3, false)}</Td>
                  <Td>{m.unseen_hours_scored ? `${m.unseen_hours_scored} unseen h` : m.score_basis}</Td>
                  <Td>{fmtUtc(m.trained_at)}</Td>
                  <Td>{m.live_accuracy.checked_predictions === 0 ? "none checked" : `${fmtFraction(m.live_accuracy.direction_right_rate)} of ${m.live_accuracy.checked_predictions}`}</Td>
                </tr>
              ) : <tr key={m.symbol}><Td>{m.symbol}</Td><Td className="text-fog-500">Not trained yet</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td></tr>)}
            </Table>
            <p className="text-xs text-fog-500">
              Skill compares the model's error with always predicting "no change"; zero or negative means no edge. MAE is the average miss of the 1 h return forecast, in percentage points.
              The backend does not report RMSE. Live direction needs about 30 checked forecasts before it means anything.
            </p>
          </div>
        ) : null}
      </Panel>

      <Panel title="Backtest scenarios" aside={bt && bt.available ? <span className="text-xs text-fog-500">Generated {fmtUtc(bt.generated_at)}</span> : null}>
        {backtest.error ? <ErrorState error={backtest.error} onRetry={backtest.refresh} showingStale={!!bt} /> : null}
        {backtest.loading ? <Skeleton lines={4} /> : null}
        {bt && !bt.available ? <EmptyState title="No backtest saved yet">{bt.note}</EmptyState> : null}
        {bt && bt.available ? (
          <div className="space-y-3">
            {anyInconclusive ? <Warning title="Some scenarios are statistically inconclusive">Rows marked below have fewer than 30 trades. Their returns could easily be luck and must not be read as evidence of an edge.</Warning> : null}
            <Table caption="Backtest results in USDT-denominated paper trading" head={["Scenario", "Return", "Buy & hold", "Max drawdown", "Trades", "Win rate", "Avg trade", "Profit factor", "Fees paid", "Reliability"]}>
              {rows.map((r) => (
                <tr key={r.scenario} className={r.inconclusive ? "opacity-80" : ""}>
                  <Td>{r.scenario}</Td>
                  <Td className={toneClass(r["return_%"])}>{fmtPct(r["return_%"])}</Td>
                  <Td>{fmtPct(r["buy_hold_%"])}</Td>
                  <Td>{fmtPct(r["max_drawdown_%"], 2, false)}</Td>
                  <Td>{r.trades ?? "n/a"}</Td>
                  <Td>{fmtPct(r["win_rate_%"], 1, false)}</Td>
                  <Td>{fmtPct(r["avg_trade_%"])}</Td>
                  <Td>{fmtNumber(r.profit_factor)}</Td>
                  <Td>{fmtNumber(r.fees_paid)}</Td>
                  <Td>
                    {r.scenario.includes("NO fees") ? <span className="text-down">Unrealistic (no costs)</span> : r.inconclusive ? <span className="text-warn">Inconclusive (&lt; 30 trades)</span> : <span className="text-fog-300">30+ trades</span>}
                  </Td>
                </tr>
              ))}
            </Table>
            <p className="text-xs text-fog-500">{bt.note} Results include the backend's assumed trading fee and slippage unless the scenario says otherwise. INR taxes such as TDS are not modelled, and these are USDT-based simulations, not CoinSwitch results. One replayed window cannot show how a strategy behaves in other markets.</p>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
