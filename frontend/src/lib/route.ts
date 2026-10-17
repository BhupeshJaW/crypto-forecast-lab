export type Route =
  | { page: "overview" }
  | { page: "coin"; symbol: string | null }
  | { page: "portfolio" }
  | { page: "analytics" }
  | { page: "alerts" }
  | { page: "status" };

const SYMBOL = /^[A-Z0-9]{2,20}$/;

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  switch (parts[0]) {
    case "coin": {
      const s = (parts[1] ?? "").toUpperCase();
      return { page: "coin", symbol: SYMBOL.test(s) ? s : null };
    }
    case "portfolio": return { page: "portfolio" };
    case "analytics": return { page: "analytics" };
    case "alerts": return { page: "alerts" };
    case "status": return { page: "status" };
    default: return { page: "overview" };
  }
}

export function hrefFor(r: Route): string {
  return r.page === "overview" ? "#/" : r.page === "coin" ? `#/coin${r.symbol ? `/${r.symbol}` : ""}` : `#/${r.page}`;
}
