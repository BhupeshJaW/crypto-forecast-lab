import type {
  AlertConfig, BacktestReport, CandlesResponse, CoinAnalysis, EquityPoint, Forecast, Health,
  ModelPerformance, PaperPortfolio, PaperTrade, RecentAlerts, Signal,
} from "../types/api";
import { authStore } from "./authToken";
import { createClient, normalizeBaseUrl } from "./http";

const client = createClient({
  baseUrl: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL),
  getToken: authStore.getToken,
  onUnauthorized: authStore.markRejected,
});

type Opt = { signal?: AbortSignal };
const sym = (s: string) => encodeURIComponent(s.toUpperCase());

/** Read-only. The backend exposes no write or trading endpoints, and neither does this client. */
export const api = {
  health: (o?: Opt) => client.get<Health>("/health", { ...o, auth: false }),
  forecasts: (o?: Opt) => client.get<Forecast[]>("/api/forecasts", o),
  signals: (o?: Opt) => client.get<Signal[]>("/api/signals", o),
  coin: (symbol: string, o?: Opt) => client.get<CoinAnalysis>(`/api/coins/${sym(symbol)}`, o),
  candles: (symbol: string, limit = 300, o?: Opt) =>
    client.get<CandlesResponse>(`/api/coins/${sym(symbol)}/candles`, { ...o, query: { limit } }),
  models: (o?: Opt) => client.get<ModelPerformance[]>("/api/models", o),
  backtest: (o?: Opt) => client.get<BacktestReport>("/api/backtest", o),
  paperPortfolio: (o?: Opt) => client.get<PaperPortfolio>("/api/paper/portfolio", o),
  paperTrades: (limit = 200, o?: Opt) => client.get<PaperTrade[]>("/api/paper/trades", { ...o, query: { limit } }),
  paperEquity: (limit = 2000, o?: Opt) => client.get<EquityPoint[]>("/api/paper/equity", { ...o, query: { limit } }),
  alertConfig: (o?: Opt) => client.get<AlertConfig>("/api/alerts/config", o),
  recentAlerts: (limit = 50, o?: Opt) => client.get<RecentAlerts>("/api/alerts/recent", { ...o, query: { limit } }),
};
