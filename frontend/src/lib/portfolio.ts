import type { PaperPortfolio } from "../types/api";

const fin = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** Equity minus the starting balance. Derived on the client from two backend fields; null until equity exists. */
export function totalPnl(p: PaperPortfolio): { abs: number; pct: number } | null {
  if (!fin(p.equity) || !fin(p.start_balance) || p.start_balance <= 0) return null;
  const abs = p.equity - p.start_balance;
  return { abs, pct: (abs / p.start_balance) * 100 };
}

/**
 * Mark-to-market gain on open positions versus their entry fill price: (equity - cash) - sum(qty * entry_fill).
 * Derived, not reported by the backend. It excludes the exit fee and slippage that closing would incur.
 */
export function unrealizedPnl(p: PaperPortfolio): number | null {
  if (!fin(p.equity) || !fin(p.cash)) return null;
  const cost = Object.values(p.open_positions ?? {}).reduce((s, pos) => s + pos.qty * pos.entry_fill, 0);
  return p.equity - p.cash - cost;
}

/** Equity vs buy-and-hold, in percent of buy-and-hold. Negative means the strategy is behind. */
export function versusBuyHold(p: PaperPortfolio): number | null {
  if (!fin(p.equity) || !fin(p.buy_hold_equity) || p.buy_hold_equity <= 0) return null;
  return (p.equity / p.buy_hold_equity - 1) * 100;
}
