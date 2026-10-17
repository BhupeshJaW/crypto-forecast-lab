export type SourceKind = "binance_usdt" | "coingecko_usd" | "coinswitch_inr" | "unknown";

export interface SourceInfo {
  kind: SourceKind;
  label: string;
  /** One line telling the reader what the price is and is not. */
  detail: string;
  /** False for everything except verified CoinSwitch INR data (none exists in the backend yet). */
  executable: boolean;
}

/**
 * Maps the backend's price_source / source strings to a label. The backend currently only produces Binance
 * USDT data (or a CoinGecko close-only fallback). Nothing is ever labelled CoinSwitch INR until the backend
 * sends a source string that explicitly says so.
 */
export function describeSource(raw: string | null | undefined): SourceInfo {
  const s = (raw ?? "").toLowerCase();
  if (s.startsWith("coinswitch")) {
    return { kind: "coinswitch_inr", label: "CoinSwitch INR", detail: "Quote from the CoinSwitch API.", executable: true };
  }
  if (s.startsWith("binance")) {
    return {
      kind: "binance_usdt",
      label: "Binance USDT",
      detail: "Reference close from Binance, in USDT. Not a CoinSwitch INR price and not an executable quote.",
      executable: false,
    };
  }
  if (s.startsWith("coingecko")) {
    return {
      kind: "coingecko_usd",
      label: "CoinGecko USD (fallback)",
      detail: "Close-only fallback with no volume. Forecasts are not valid on this data.",
      executable: false,
    };
  }
  return { kind: "unknown", label: "Unverified source", detail: "The data source is not identified.", executable: false };
}
