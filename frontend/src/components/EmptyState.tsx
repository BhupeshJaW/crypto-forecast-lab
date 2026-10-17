import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded border border-dashed border-ink-600 px-4 py-6 text-center">
      <p className="text-sm font-medium text-fog-300">{title}</p>
      {children ? <p className="mx-auto mt-1 max-w-prose text-sm text-fog-500">{children}</p> : null}
    </div>
  );
}
