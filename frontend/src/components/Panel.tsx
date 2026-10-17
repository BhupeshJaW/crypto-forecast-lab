import type { ReactNode } from "react";

export function Panel({ title, aside, children, className = "" }: { title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-md border border-ink-700 bg-ink-900 ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-ink-700 px-4 py-2.5">
        <h2 className="text-sm font-semibold text-fog-100">{title}</h2>
        {aside}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value, tone = "flat", hint }: { label: string; value: ReactNode; tone?: "up" | "down" | "flat"; hint?: ReactNode }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-fog-100";
  return (
    <div>
      <dt className="text-xs text-fog-500">{label}</dt>
      <dd className={`mt-0.5 text-lg font-medium ${color}`}>{value}</dd>
      {hint ? <p className="mt-0.5 text-xs text-fog-500">{hint}</p> : null}
    </div>
  );
}
