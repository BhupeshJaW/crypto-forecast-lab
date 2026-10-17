import type { ReactNode } from "react";

export function Warning({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div role="note" className="rounded border border-warn/40 bg-warn/10 px-4 py-3">
      <p className="text-sm font-medium text-warn">{title}</p>
      {children ? <div className="mt-1 text-sm text-fog-300">{children}</div> : null}
    </div>
  );
}
