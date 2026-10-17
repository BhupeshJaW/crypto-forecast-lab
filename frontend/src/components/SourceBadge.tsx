import { describeSource } from "../lib/source";

/** Every price on screen carries one of these, so Binance USDT references are never mistaken for CoinSwitch INR quotes. */
export function SourceBadge({ source }: { source: string | null | undefined }) {
  const info = describeSource(source);
  const style =
    info.kind === "coinswitch_inr" ? "border-up/50 text-up"
    : info.kind === "binance_usdt" ? "border-brass-500/50 text-brass-400"
    : "border-down/50 text-down";
  return (
    <span title={info.detail} className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs ${style}`}>
      {info.label}
      {info.executable ? null : <span className="ml-1 text-fog-500">reference only</span>}
    </span>
  );
}
