import { useState, type ReactNode } from "react";
import { useAuth } from "../hooks/useAuth";
import { TokenGate } from "./TokenGate";

export interface NavItem {
  id: string;
  label: string;
}

export function Layout({ nav, active, onNavigate, children }: { nav: NavItem[]; active: string; onNavigate: (id: string) => void; children: ReactNode }) {
  const [tokenOpen, setTokenOpen] = useState(false);
  const { token } = useAuth();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-ink-700 bg-ink-900/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2.5">
          <span className="text-sm font-semibold tracking-wide text-brass-400">Crypto Predictor</span>
          <nav aria-label="Primary" className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
            {nav.map((n) => (
              <button
                key={n.id} type="button" onClick={() => onNavigate(n.id)} aria-current={n.id === active ? "page" : undefined}
                className={`whitespace-nowrap rounded px-3 py-1.5 text-sm ${n.id === active ? "bg-ink-700 text-fog-100" : "text-fog-300 hover:bg-ink-800"}`}
              >
                {n.label}
              </button>
            ))}
          </nav>
          <span className="hidden rounded border border-ink-600 px-2 py-0.5 text-xs text-fog-300 sm:inline">Paper trading only</span>
          <button type="button" onClick={() => setTokenOpen(true)} className="rounded border border-ink-600 px-2.5 py-1 text-xs hover:bg-ink-700">
            {token ? "Token set" : "Token"}
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5">{children}</main>

      <footer className="border-t border-ink-700 px-4 py-3 text-xs text-fog-500">
        <p className="mx-auto max-w-7xl">
          Learning project, not financial advice. Forecasts can be wrong and the models may have no edge. Prices shown are Binance USDT references, not
          CoinSwitch INR quotes. This app is read-only and cannot place orders.
        </p>
      </footer>
      <TokenGate open={tokenOpen} onClose={() => setTokenOpen(false)} />
    </div>
  );
}
