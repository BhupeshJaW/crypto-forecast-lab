import { useEffect, useMemo, useRef } from "react";
import { AreaSeries, LineSeries, createChart, type UTCTimestamp } from "lightweight-charts";
import { drawdownSeries, type EquityPt } from "../lib/chartData";
import { C, baseChartOptions } from "./theme";

/** Paper equity vs buy-and-hold, with drawdown from peak underneath. Real /api/paper/equity rows only. */
export function EquityChart({ points }: { points: EquityPt[] }) {
  const host = useRef<HTMLDivElement>(null);
  const dd = useMemo(() => drawdownSeries(points), [points]);

  useEffect(() => {
    const el = host.current;
    if (!el || points.length === 0) return;
    const chart = createChart(el, baseChartOptions);
    chart.addSeries(LineSeries, { color: C.brass, lineWidth: 2, title: "Paper equity" })
      .setData(points.map((p) => ({ time: p.time as UTCTimestamp, value: p.equity })));
    chart.addSeries(LineSeries, { color: C.muted, lineWidth: 1, title: "Buy & hold" })
      .setData(points.filter((p) => p.buyHold !== null).map((p) => ({ time: p.time as UTCTimestamp, value: p.buyHold as number })));
    chart.addSeries(AreaSeries, { lineColor: C.down, topColor: "rgba(229,100,95,0.05)", bottomColor: "rgba(229,100,95,0.35)", title: "Drawdown %", priceLineVisible: false }, 1)
      .setData(dd.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    try {
      const panes = chart.panes();
      panes[0]?.setHeight(260);
      panes[1]?.setHeight(100);
    } catch {
      /* cosmetic */
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points, dd]);

  return <div ref={host} role="img" aria-label="Paper equity and drawdown chart" style={{ height: 390 }} className="w-full" />;
}
