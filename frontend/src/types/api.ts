/**
 * Response types for the FastAPI backend (api.py / services.py), written from the actual code and from
 * real payloads. NaN/inf are serialised by the backend as null, so any numeric field that comes from
 * pandas can be null. Optional (?) fields are only present in some situations; see the comments.
 */

export type SignalKind = "BUY" | "SELL" | "HOLD" | "NO_TRADE";
export type SellType = "exit_position" | "bearish_not_held";
export type ModelGrade = "high" | "medium" | "low";

/** ISO-8601 timestamp string with UTC offset, e.g. "2026-10-16T21:01:11.224554+00:00". */
export type IsoTime = string;

// ---------- GET /health (no auth) ----------
export interface Health {
  status: "ok" | "degraded" | string;
  worker_last_success: IsoTime | null;
  worker_age_hours: number | null;
  max_age_hours: number;
  tracked_coins: number;
  alert_channels: string[];
  coinswitch_configured: boolean;
}

// ---------- GET /api/forecasts ----------
export interface ForecastMissing {
  symbol: string;
  available: false;
}
export interface ForecastAvailable {
  symbol: string;
  available: true;
  created_at: IsoTime;
  target_time: IsoTime;
  /** Binance USDT close of the last closed candle. NOT a CoinSwitch INR price. */
  reference_price: number | null;
  price_source: string; // "binance_usdt_last_closed_candle"
  predicted_price: number | null;
  /** Already a percentage (0.12 means +0.12%). */
  predicted_return_pct: number | null;
  model: string;
  model_version: string;
  forecast_age_hours: number | null;
  resolved: boolean;
}
export type Forecast = ForecastMissing | ForecastAvailable;

// ---------- GET /api/signals ----------
/** Returned for a coin before the worker has produced a signal. */
export interface SignalMissing {
  symbol: string;
  signal: null;
  note: string;
}
export interface SignalPresent {
  symbol: string;
  signal: SignalKind;
  sell_type: SellType | null;
  reference_price: number | null;
  price_source: string; // "binance_usdt_close"
  price_note: string;
  horizon_hours: number;
  /** Percentages (0.12 means +0.12%). */
  predicted_return_pct: number | null;
  /** [low, high] in percent: a typical-error band around the forecast, not a confidence interval. */
  typical_error_band_pct: [number, number] | null;
  estimated_round_trip_cost_pct: number;
  net_edge_after_costs_pct: number | null;
  model_grade: ModelGrade;
  holdout_hours: number | null;
  grade_note: string;
  data_age_hours: number | null;
  created_at: IsoTime;
  expires_at: IsoTime;
  reasons: string[];
  /** Non-empty means NO_TRADE was forced by a hard safety rule. */
  blockers: string[];
  // Present on BUY signals only:
  entry_zone?: [number, number];
  stop_loss?: number;
  take_profit?: number;
  reward_to_risk?: number;
}
export type Signal = SignalMissing | SignalPresent;

// ---------- GET /api/models ----------
export interface LiveAccuracy {
  checked_predictions: number;
  direction_right_rate: number | null; // 0..1
  beats_coin_flip: boolean | null; // null until enough samples
  verdict: string;
  mean_abs_error_pct: number | null;
}
export interface ModelMissing {
  symbol: string;
  available: false;
}
export interface ModelAvailable {
  symbol: string;
  available: true;
  model: string;
  version: string;
  trained_at: IsoTime;
  /** null for legacy cross-validation scores (see score_basis). */
  unseen_hours_scored: number | null;
  /** Mean absolute error of the hourly return forecast (fraction, not percent). The backend does not provide RMSE. */
  mae: number | null;
  naive_mae: number | null;
  skill_vs_naive_pct: number | null;
  /** 0..1 */
  direction_accuracy: number | null;
  grade: ModelGrade;
  score_basis: string;
  live_accuracy: LiveAccuracy;
  history_runs: number;
}
export type ModelPerformance = ModelMissing | ModelAvailable;

// ---------- GET /api/coins/{symbol} ----------
export interface CoinAnalysis {
  symbol: string;
  forecast: Forecast;
  signal: Signal;
  model: ModelPerformance;
  disclaimer: string;
}

// ---------- GET /api/coins/{symbol}/candles ----------
export interface Candle {
  /** Unix seconds (UTC) of the candle open: pass straight to lightweight-charts as UTCTimestamp. */
  time: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  // Indicators are null during the warm-up window at the start of the series.
  sma20?: number | null;
  sma50?: number | null;
  bb_up?: number | null;
  bb_lo?: number | null;
  rsi14?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
}
export type Regime = "bullish" | "bearish" | "sideways" | "unknown";
export interface CandlesResponse {
  symbol: string;
  interval: string; // "1h"
  /** "binance" normally; "coingecko" means a close-only fallback with no volume. */
  source: string;
  note: string;
  last_candle_time: IsoTime;
  data_age_hours: number | null;
  fetched_at: IsoTime;
  regime: Regime;
  candles: Candle[];
}

// ---------- GET /api/backtest ----------
export interface BacktestRow {
  scenario: string;
  "return_%": number | null;
  "buy_hold_%": number | null;
  "max_drawdown_%": number | null;
  sharpe: number | null;
  trades: number | null;
  "win_rate_%": number | null;
  "avg_trade_%": number | null;
  profit_factor: number | null;
  fees_paid: number | null;
  /** True when fewer than 30 trades: not statistically meaningful. */
  inconclusive: boolean;
}
export type BacktestReport =
  | { available: false; note: string }
  | { available: true; rows: BacktestRow[]; note: string; generated_at: IsoTime };

// ---------- GET /api/paper/portfolio ----------
export interface PaperPosition {
  qty: number;
  entry_fill: number;
  entry_fee: number;
  entry_time: IsoTime;
}
export interface PaperPortfolio {
  start_balance: number;
  /** "USDT (paper)". The paper account is NOT INR-denominated in the current backend. */
  currency: string;
  open_positions: Record<string, PaperPosition>;
  trades: number;
  // Present only once at least one equity row exists:
  equity?: number | null;
  cash?: number | null;
  buy_hold_equity?: number | null;
  max_drawdown_pct?: number | null;
  current_drawdown_pct?: number | null;
  last_update?: IsoTime;
  realized_pnl: number | null;
  fees_paid: number | null;
  win_rate_pct: number | null;
  statistically_conclusive: boolean;
  note: string;
}

// ---------- GET /api/paper/trades ----------
export interface PaperTrade {
  id: number;
  symbol: string;
  entry_time: IsoTime;
  exit_time: IsoTime;
  entry_price: number | null;
  exit_price: number | null;
  qty: number | null;
  fees: number | null;
  pnl: number | null;
  /** Fraction (0.01 = 1%), unlike the *_pct fields elsewhere. */
  pnl_pct: number | null;
  reason: string; // stop_loss | take_profit | signal_exit
  hold_hours: number | null;
}

// ---------- GET /api/paper/equity ----------
export interface EquityPoint {
  ts: IsoTime;
  cash: number | null;
  equity: number | null;
  bh_equity: number | null;
  open_positions: number | null;
}

// ---------- GET /api/alerts/config ----------
export interface AlertConfig {
  channels: string[];
  drawdown_alert_pct: number;
  signal_alerts: string;
  editable_via_api: boolean;
}

/** GET /api/alerts/recent returns raw log lines ("YYYY-MM-DD HH:MM:SS,mmm | LEVEL | message"), not objects. */
export type RecentAlerts = string[];
