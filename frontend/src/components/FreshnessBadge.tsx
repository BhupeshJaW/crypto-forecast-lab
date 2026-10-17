import { fmtAge } from "../lib/format";
import { freshness } from "../lib/freshness";

export function FreshnessBadge({ ageHours, maxHours, label = "Data" }: { ageHours: number | null | undefined; maxHours: number; label?: string }) {
  const f = freshness(ageHours, maxHours);
  const dot = f === "fresh" ? "bg-up" : f === "aging" ? "bg-warn" : f === "stale" ? "bg-down" : "bg-fog-500";
  const word = f === "stale" ? "stale" : f === "aging" ? "ageing" : f === "fresh" ? "fresh" : "unknown";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-fog-300">
      <span aria-hidden className={`h-2 w-2 rounded-full ${dot}`} />
      {label} {fmtAge(ageHours)} ({word})
      {f === "stale" ? <span className="text-down">Do not act on this.</span> : null}
    </span>
  );
}
