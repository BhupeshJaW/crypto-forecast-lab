import { useMemo } from "react";
import { EquityChart } from "../charts/EquityChart";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Panel, Stat } from "../components/Panel";
import { Skeleton } from "../components/Skeleton";
import { Table, Td } from "../components/Table";
import { Warning } from "../components/Warning";
import { useApi } from "../hooks/useApi";
import { equityPoints } from "../lib/chartData";
import { fmtNumber, fmtPct, fmtPrice, fmtUtc, tone } from "../lib/format";
import { totalPnl, unrealizedPnl, versusBuyHold } from "../lib/portfolio";
import { api } from "../services/api";

export function PortfolioPage() {
  const pf = useApi((s) => api.paperPortfolio({ signal: s }), { pollMs: 60_000 });
  const trades = useApi((s) => api.paperTrades(200, { signal: s }), { pollMs: 120_000 });
  const equity = useApi((s) => api.paperEquity(2000, { signal: s }), { pollMs: 120_000 });
  const points = useMemo(() => equityPoints(equity.data ?? []), [equity.data]);

  const p = pf.data;
  const unit = p?.currency.split(" ")[0] ?? "USDT";
  const pnl = p ? totalPnl(p) : null;
  const unreal = p ? unrealizedPnl(p) : null;
  const vsBh = p ? versusBuyHold(p) : null;
  const positions = p ? Object.entries(p.open_positions) : [];

  return (
    <div className="space-y-4">
      <Warning title={`Simulated ${unit} account, not INR`}>
        This paper account is denominated in {unit} with simulated fees and slippage. Nothing here is a CoinSwitch balance, and INR taxes (such as TDS) are not modelled yet.
      </Warning>

      <Panel title="Account" aside={p?.last_update ? <span className="text-xs text-fog-500">Updated {fmtUtc(p.last_update)}</span> : null}>
        {pf.error ? <ErrorState error={pf.error} onRetry={pf.refresh} showingStale={!!p} /> : null}
        {pf.loading ? <Skeleton lines={3} /> : null}
        {p ? (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Stat label="Equity" value={fmtPrice(p.equity, unit)} hint={`Started with ${fmtNumber(p.start_balance, 0)} ${unit}`} />
              <Stat label="Cash" value={fmtPrice(p.cash, unit)} />
              <Stat label="Total P&L" value={pnl ? `${fmtPrice(pnl.abs, unit)} (${fmtPct(pnl.pct)})` : "n/a"} tone={tone(pnl?.abs)} />
              <Stat label="Versus buy & hold" value={fmtPct(vsBh)} tone={tone(vsBh)} hint={`Buy & hold: ${fmtPrice(p.buy_hold_equity, unit)}`} />
              <Stat label="Realized P&L" value={fmtPrice(p.realized_pnl, unit)} tone={tone(p.realized_pnl)} />
              <Stat label="Unrealized P&L" value={fmtPrice(unreal, unit)} tone={tone(unreal)} hint="Derived: open positions vs entry fill, before exit costs" />
              <Stat label="Fees paid" value={fmtPrice(p.fees_paid, unit)} />
              <Stat label="Win rate" value={p.win_rate_pct === null ? "n/a" : fmtPct(p.win_rate_pct, 1, false)} hint={`${p.trades} closed trades`} />
              <Stat label="Max drawdown" value={fmtPct(p.max_drawdown_pct, 2, false)} tone={tone(p.max_drawdown_pct)} />
              <Stat label="Current drawdown" value={fmtPct(p.current_drawdown_pct, 2, false)} tone={tone(p.current_drawdown_pct)} />
            </dl>
            {!p.statistically_conclusive ? <Warning title="Statistically inconclusive">{p.note}</Warning> : null}
          </div>
        ) : null}
      </Panel>

      <Panel title="Equity curve and drawdown">
        {equity.error ? <ErrorState error={equity.error} onRetry={equity.refresh} showingStale={!!equity.data} /> : null}
        {equity.loading ? <Skeleton lines={5} /> : null}
        {equity.data && points.length === 0 ? <EmptyState title="No equity history yet">The worker records one point per cycle.</EmptyState> : null}
        {points.length === 1 ? <p className="mb-2 text-xs text-fog-500">Only one point so far; a curve needs at least two.</p> : null}
        {points.length > 0 ? <EquityChart points={points} /> : null}
      </Panel>

      <Panel title="Open positions">
        {positions.length === 0 ? <EmptyState title="No open positions" /> : (
          <Table head={["Symbol", "Quantity", "Entry fill", "Entry fee", "Opened"]}>
            {positions.map(([sym, pos]) => (
              <tr key={sym}><Td>{sym}</Td><Td>{fmtNumber(pos.qty, 6)}</Td><Td>{fmtPrice(pos.entry_fill, unit)}</Td><Td>{fmtPrice(pos.entry_fee, unit)}</Td><Td>{fmtUtc(pos.entry_time)}</Td></tr>
            ))}
          </Table>
        )}
      </Panel>

      <Panel title="Trade history">
        {trades.error ? <ErrorState error={trades.error} onRetry={trades.refresh} showingStale={!!trades.data} /> : null}
        {trades.loading ? <Skeleton lines={3} /> : null}
        {trades.data && trades.data.length === 0 ? <EmptyState title="No closed trades yet">The strategy only trades when a model shows a validated edge.</EmptyState> : null}
        {trades.data && trades.data.length > 0 ? (
          <Table caption="Closed paper trades, newest first" head={["Symbol", "Opened", "Closed", "Entry", "Exit", "Qty", "Fees", "P&L", "P&L %", "Held", "Exit reason"]}>
            {trades.data.map((t) => (
              <tr key={t.id}>
                <Td>{t.symbol}</Td><Td>{fmtUtc(t.entry_time)}</Td><Td>{fmtUtc(t.exit_time)}</Td>
                <Td>{fmtNumber(t.entry_price, 4)}</Td><Td>{fmtNumber(t.exit_price, 4)}</Td><Td>{fmtNumber(t.qty, 6)}</Td><Td>{fmtNumber(t.fees)}</Td>
                <Td className={tone(t.pnl) === "up" ? "text-up" : tone(t.pnl) === "down" ? "text-down" : ""}>{fmtNumber(t.pnl)}</Td>
                {/* pnl_pct is a fraction in this endpoint */}
                <Td>{fmtPct(t.pnl_pct === null ? null : t.pnl_pct * 100)}</Td>
                <Td>{t.hold_hours === null ? "n/a" : `${fmtNumber(t.hold_hours, 1)} h`}</Td><Td>{t.reason.replace("_", " ")}</Td>
              </tr>
            ))}
          </Table>
        ) : null}
      </Panel>
    </div>
  );
}
