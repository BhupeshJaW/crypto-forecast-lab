import { useEffect, useRef } from "react";
import {
  CandlestickSeries, HistogramSeries, LineSeries, LineStyle, createChart,
  type IChartApi, type UTCTimestamp,
} from "lightweight-charts";
import type { LinePt, PreparedCandles } from "../lib/chartData";
import { C, baseChartOptions } from "./theme";

export interface PriceLevels { entryLow?: number; entryHigh?: number; stop?: number; target?: number }
export interface Layers { sma: boolean; bands: boolean; volume: boolean; rsi: boolean; macd: boolean }

const t = (d: LinePt[]) => d.map((p) => ({ time: p.time as UTCTimestamp, value: p.value }));

/**
 * Candles, indicators and (for a BUY signal) the backend's entry/stop/target levels. All data comes from
 * /api/coins/{symbol}/candles; times are Unix seconds (UTC), which the chart renders as UTC.
 * The chart is rebuilt when new data arrives, so zoom resets on each refresh.
 */
export function CandleChart({ data, levels, layers }: { data: PreparedCandles; levels?: PriceLevels; layers: Layers }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const chart: IChartApi = createChart(el, baseChartOptions);

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: C.up, downColor: C.down, borderUpColor: C.up, borderDownColor: C.down, wickUpColor: C.up, wickDownColor: C.down,
    });
    candles.setData(data.ohlc.map((c) => ({ ...c, time: c.time as UTCTimestamp })));

    if (layers.sma) {
      chart.addSeries(LineSeries, { color: C.brass, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "SMA20" }).setData(t(data.sma20));
      chart.addSeries(LineSeries, { color: C.blue, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "SMA50" }).setData(t(data.sma50));
    }
    if (layers.bands) {
      for (const d of [data.bbUp, data.bbLo]) {
        chart.addSeries(LineSeries, { color: C.muted, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false }).setData(t(d));
      }
    }
    if (layers.volume) {
      const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "", lastValueVisible: false, priceLineVisible: false });
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      vol.setData(data.volume.map((v) => ({ time: v.time as UTCTimestamp, value: v.value, color: v.up ? C.upFill : C.downFill })));
    }

    const line = (price: number | undefined, color: string, title: string) => {
      if (typeof price === "number" && Number.isFinite(price)) {
        candles.createPriceLine({ price, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title });
      }
    };
    line(levels?.entryLow, C.brass, "Entry");
    line(levels?.entryHigh, C.brass, "Entry max");
    line(levels?.stop, C.down, "Stop");
    line(levels?.target, C.up, "Target");

    let pane = 0;
    const sizes: number[] = [];
    if (layers.rsi) {
      pane += 1;
      const rsi = chart.addSeries(LineSeries, { color: C.violet, lineWidth: 1, title: "RSI 14", priceLineVisible: false }, pane);
      rsi.setData(t(data.rsi));
      rsi.createPriceLine({ price: 70, color: C.muted, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" });
      rsi.createPriceLine({ price: 30, color: C.muted, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" });
      sizes.push(pane);
    }
    if (layers.macd) {
      pane += 1;
      chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane)
        .setData(data.macdHist.map((p) => ({ time: p.time as UTCTimestamp, value: p.value, color: p.value >= 0 ? C.upFill : C.downFill })));
      chart.addSeries(LineSeries, { color: C.blue, lineWidth: 1, title: "MACD", priceLineVisible: false, lastValueVisible: false }, pane).setData(t(data.macd));
      chart.addSeries(LineSeries, { color: C.brass, lineWidth: 1, title: "Signal", priceLineVisible: false, lastValueVisible: false }, pane).setData(t(data.macdSignal));
      sizes.push(pane);
    }
    try {
      const panes = chart.panes();
      panes[0]?.setHeight(340);
      for (const i of sizes) panes[i]?.setHeight(110);
    } catch {
      /* pane sizing is cosmetic; the chart still renders with default heights */
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, levels, layers]);

  const height = 340 + 110 * ((layers.rsi ? 1 : 0) + (layers.macd ? 1 : 0)) + 30;
  return <div ref={host} role="img" aria-label="Candlestick chart of hourly closed candles" style={{ height }} className="w-full" />;
}
