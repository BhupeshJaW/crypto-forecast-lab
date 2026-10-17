import type { ModelGrade, SignalKind } from "../types/api";

const SIGNAL_STYLE: Record<SignalKind, string> = {
  BUY: "border-up/60 bg-up/15 text-up",
  SELL: "border-down/60 bg-down/15 text-down",
  HOLD: "border-brass-500/50 bg-brass-500/10 text-brass-400",
  NO_TRADE: "border-ink-600 bg-ink-800 text-fog-300",
};

export function SignalBadge({ kind, expired = false }: { kind: SignalKind | null; expired?: boolean }) {
  if (kind === null) return <span className="rounded border border-ink-600 px-2 py-0.5 text-xs text-fog-500">No signal yet</span>;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs font-semibold ${SIGNAL_STYLE[kind]} ${expired ? "opacity-60" : ""}`}>
      {kind === "NO_TRADE" ? "NO TRADE" : kind}
      {expired ? <span className="font-normal text-fog-300">expired</span> : null}
    </span>
  );
}

const GRADE_TEXT: Record<ModelGrade, string> = {
  high: "Validated edge: high",
  medium: "Validated edge: medium",
  low: "No validated edge",
};
export function GradeBadge({ grade }: { grade: ModelGrade }) {
  const style = grade === "low" ? "border-down/40 text-down" : grade === "medium" ? "border-warn/50 text-warn" : "border-up/50 text-up";
  return <span title="Grade from unseen-data tests. It is not the chance of making money." className={`rounded border px-1.5 py-0.5 text-xs ${style}`}>{GRADE_TEXT[grade]}</span>;
}
