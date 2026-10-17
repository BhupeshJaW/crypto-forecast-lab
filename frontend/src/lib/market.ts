const fin = (n: number | null | undefined): n is number => typeof n === "number" && Number.isFinite(n);

/** Percent change between the latest close and the close `lookback` candles earlier. null if either is missing. */
export function changePct(closes: (number | null | undefined)[], lookback: number): number | null {
  const last = closes[closes.length - 1];
  const prev = closes[closes.length - 1 - lookback];
  if (!fin(last) || !fin(prev) || prev <= 0) return null;
  return (last / prev - 1) * 100;
}

/** The base asset of a Binance spot symbol, for display only ("BTCUSDT" -> "BTC"). */
export const baseAsset = (symbol: string): string => symbol.replace(/USDT$/, "");
