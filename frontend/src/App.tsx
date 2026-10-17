import { Layout, type NavItem } from "./components/Layout";
import { useHashRoute } from "./hooks/useHashRoute";
import type { Route } from "./lib/route";
import { AlertsPage } from "./pages/AlertsPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { CoinPage } from "./pages/CoinPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { StatusPage } from "./pages/StatusPage";

const NAV: NavItem[] = [
  { id: "overview", label: "Overview" },
  { id: "coin", label: "Coin analysis" },
  { id: "portfolio", label: "Paper portfolio" },
  { id: "analytics", label: "Models and backtests" },
  { id: "alerts", label: "Alerts" },
  { id: "status", label: "Status" },
];

function Page({ route }: { route: Route }) {
  switch (route.page) {
    case "overview": return <OverviewPage />;
    case "coin": return <CoinPage symbol={route.symbol} />;
    case "portfolio": return <PortfolioPage />;
    case "analytics": return <AnalyticsPage />;
    case "alerts": return <AlertsPage />;
    case "status": return <StatusPage />;
  }
}

export default function App() {
  const [route, go] = useHashRoute();
  const navigate = (id: string) => go(id === "coin" ? { page: "coin", symbol: route.page === "coin" ? route.symbol : null } : ({ page: id } as Route));
  return (
    <Layout nav={NAV} active={route.page} onNavigate={navigate}>
      <Page route={route} />
    </Layout>
  );
}
