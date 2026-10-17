const DASH = "n/a";
const ok = (n: number | null | undefined): n is number => typeof n === "number" && Number.isFinite(n);

export function fmtNumber(n: number | null | undefined, digits = 2): string {
  return ok(n) ? n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : DASH;
}

/** Percent value that is already in percent units (0.12 -> "+0.12%"). */
export function fmtPct(n: number | null | undefined, digits = 2, signed = true): string {
  if (!ok(n)) return DASH;
  const s = n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${signed && n > 0 ? "+" : ""}${s}%`;
}

/** A 0..1 fraction shown as a percent. */
export const fmtFraction = (n: number | null | undefined, digits = 1) => fmtPct(ok(n) ? n * 100 : n, digits, false);

/** More decimals for cheap coins. The unit is always shown, never implied. */
export function fmtPrice(n: number | null | undefined, unit = "USDT"): string {
  if (!ok(n)) return DASH;
  const digits = Math.abs(n) >= 1000 ? 2 : Math.abs(n) >= 1 ? 3 : 6;
  return `${fmtNumber(n, digits)} ${unit}`;
}

export function fmtMoney(n: number | null | undefined, unit: string, digits = 2): string {
  return ok(n) ? `${fmtNumber(n, digits)} ${unit}` : DASH;
}

/** Always UTC and labelled, so the page never silently mixes time zones. */
export function fmtUtc(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return DASH;
  return new Date(t).toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

export function fmtAge(hours: number | null | undefined): string {
  if (!ok(hours)) return "unknown age";
  if (hours < 0) return "just now";
  if (hours < 1 / 60) return "under a minute ago";
  if (hours < 1) return `${Math.round(hours * 60)} min ago`;
  if (hours < 48) return `${hours.toFixed(1)} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** Sign class for P&L-style numbers. Zero and unknown stay neutral. */
export function tone(n: number | null | undefined): "up" | "down" | "flat" {
  if (!ok(n) || n === 0) return "flat";
  return n > 0 ? "up" : "down";
}
