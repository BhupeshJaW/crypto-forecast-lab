import type { Candle, EquityPoint } from "../types/api";

export interface LinePt { time: number; value: number }
export interface OhlcPt { time: number; open: number; high: number; low: number; close: number }
export interface VolPt { time: number; value: number; up: boolean }

const fin = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** lightweight-charts throws on unsorted or duplicate times, so sort ascending and keep the last row per time. */
export function ascendingUnique<T extends { time: number }>(rows: T[]): T[] {
  const byTime = new Map<number, T>();
  for (const r of rows) if (fin(r.time)) byTime.set(r.time, r);
  return [...byTime.values()].sort((a, b) => a.time - b.time);
}

function line(candles: Candle[], pick: (c: Candle) => number | null | undefined): LinePt[] {
  const out: LinePt[] = [];
  for (const c of candles) {
    const v = pick(c);
    if (fin(v)) out.push({ time: c.time, value: v });
  }
  return ascendingUnique(out);
}

export interface PreparedCandles {
  ohlc: OhlcPt[];
  volume: VolPt[];
  sma20: LinePt[]; sma50: LinePt[]; bbUp: LinePt[]; bbLo: LinePt[];
  rsi: LinePt[]; macd: LinePt[]; macdSignal: LinePt[];
  macdHist: LinePt[];
  /** Rows that could not be drawn (null or inconsistent OHLC). Shown to the user instead of hiding gaps. */
  dropped: number;
}

export function prepareCandles(candles: Candle[]): PreparedCandles {
  const ohlc: OhlcPt[] = [];
  const volume: VolPt[] = [];
  let dropped = 0;
  for (const c of candles) {
    if (!fin(c.open) || !fin(c.high) || !fin(c.low) || !fin(c.close) || c.high < c.low) { dropped += 1; continue; }
    ohlc.push({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close });
    if (fin(c.volume)) volume.push({ time: c.time, value: c.volume, up: c.close >= c.open });
  }
  return {
    ohlc: ascendingUnique(ohlc), volume: ascendingUnique(volume),
    sma20: line(candles, (c) => c.sma20), sma50: line(candles, (c) => c.sma50),
    bbUp: line(candles, (c) => c.bb_up), bbLo: line(candles, (c) => c.bb_lo),
    rsi: line(candles, (c) => c.rsi14), macd: line(candles, (c) => c.macd),
    macdSignal: line(candles, (c) => c.macd_signal), macdHist: line(candles, (c) => c.macd_hist),
    dropped,
  };
}

/** ISO timestamp -> Unix seconds, or null if unparseable. */
export function isoToSeconds(iso: string): number | null {
  const t = Date.parse(iso);
  return Number.isFinite(t) ? Math.floor(t / 1000) : null;
}

export interface EquityPt { time: number; equity: number; buyHold: number | null }

export function equityPoints(rows: EquityPoint[]): EquityPt[] {
  const out: EquityPt[] = [];
  for (const r of rows) {
    const time = isoToSeconds(r.ts);
    if (time === null || !fin(r.equity)) continue;
    out.push({ time, equity: r.equity, buyHold: fin(r.bh_equity) ? r.bh_equity : null });
  }
  return ascendingUnique(out);
}

/** Percent below the running peak (<= 0). */
export function drawdownSeries(points: { time: number; equity: number }[]): LinePt[] {
  let peak = -Infinity;
  return points.map((p) => {
    peak = Math.max(peak, p.equity);
    return { time: p.time, value: peak > 0 ? (p.equity / peak - 1) * 100 : 0 };
  });
}
