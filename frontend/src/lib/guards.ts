import type {
  Forecast, ForecastAvailable, ModelAvailable, ModelPerformance, Signal, SignalPresent,
} from "../types/api";

export const isForecastAvailable = (f: Forecast | undefined): f is ForecastAvailable => !!f && f.available === true;
export const isModelAvailable = (m: ModelPerformance | undefined): m is ModelAvailable => !!m && m.available === true;
export const isSignalPresent = (s: Signal | undefined): s is SignalPresent => !!s && s.signal !== null;
export const bySymbol = <T extends { symbol: string }>(rows: T[] | null | undefined, symbol: string): T | undefined =>
  rows?.find((r) => r.symbol === symbol);
