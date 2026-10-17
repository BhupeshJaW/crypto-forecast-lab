export type LogLevel = "INFO" | "WARNING" | "ERROR" | "OTHER";
export type AlertKind = "alert" | "fetch_failed" | "error";

export interface AlertLine {
  /** Exactly as written in the log. The log carries no time zone, so it is never converted or labelled UTC. */
  loggedAt: string | null;
  level: LogLevel;
  kind: AlertKind;
  message: string;
}

const LINE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} \| ([A-Z]+) \| (.*)$/;

export function parseAlertLine(raw: string): AlertLine {
  const text = raw.replace(/\r$/, "").slice(0, 500);
  const m = LINE.exec(text);
  const level = (m?.[2] ?? "OTHER") as string;
  const message = m?.[3] ?? text;
  const lvl: LogLevel = level === "INFO" || level === "WARNING" || level === "ERROR" ? level : "OTHER";
  const kind: AlertKind = message.includes("[alert]") ? "alert" : message.includes("fetch failed") ? "fetch_failed" : "error";
  return { loggedAt: m?.[1] ?? null, level: lvl, kind, message };
}

/** Newest first (the backend returns oldest first). */
export const parseAlertLines = (lines: string[]): AlertLine[] => lines.map(parseAlertLine).reverse();
