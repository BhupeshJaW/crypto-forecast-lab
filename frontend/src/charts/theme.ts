export const C = {
  text: "#aab3c0", grid: "#171d26", border: "#232b37",
  up: "#3fb68b", down: "#e5645f", brass: "#e0a84a", blue: "#6aa5e8", violet: "#a98bd9", muted: "#7b8696",
  upFill: "rgba(63,182,139,0.45)", downFill: "rgba(229,100,95,0.45)",
} as const;

export const baseChartOptions = {
  autoSize: true,
  layout: { textColor: C.text, background: { color: "transparent" }, attributionLogo: true },
  grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
  rightPriceScale: { borderColor: C.border },
  timeScale: { borderColor: C.border, timeVisible: true, secondsVisible: false },
  crosshair: { mode: 0 },
} as const;
