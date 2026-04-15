import { Suspense, lazy, useEffect, useState } from "react";
import { Route, Routes, Navigate } from "react-router-dom";
import { checkAuthStatus, isAuthenticated } from "./api/auth";
import ErrorBoundary from "./components/ui/ErrorBoundary";
import { ToastProvider } from "./components/ui/Toast";
import { AppDataProvider } from "./store/AppDataStore";
import AppLayout from "./components/layout/AppLayout";

// Lazy load pages
const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const KPIDashboardPage = lazy(() => import("./pages/KPIDashboardPage"));
const AINewsPage = lazy(() => import("./pages/AINewsPage"));
const LiveMarketPage = lazy(() => import("./pages/LiveMarketPage"));
const PaperTradingPage = lazy(() => import("./pages/PaperTradingPage"));
const BacktestPage = lazy(() => import("./pages/BacktestPage"));
const StrategyLabPage = lazy(() => import("./pages/StrategyLabPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
// Keep additional pages accessible
const AnalyzePage = lazy(() => import("./pages/AnalyzePage"));
const RankingPage = lazy(() => import("./pages/RankingPage"));
const BreadthPage = lazy(() => import("./pages/BreadthPage"));
const RiskDashboardPage = lazy(() => import("./pages/RiskDashboardPage"));
const ModelLabPage = lazy(() => import("./pages/ModelLabPage"));
const AlertsCenterPage = lazy(() => import("./pages/AlertsCenterPage"));
const TradeJournalPage = lazy(() => import("./pages/TradeJournalPage"));
const AutomationPage = lazy(() => import("./pages/AutomationPage"));
const BrokerPage = lazy(() => import("./pages/BrokerPage"));
const OperationsPage = lazy(() => import("./pages/OperationsPage"));
const PortfolioExposurePage = lazy(() => import("./pages/PortfolioExposurePage"));

const BrainDashboardPage = lazy(() => import("./pages/BrainDashboardPage"));
const AIMarketPage = lazy(() => import("./pages/AIMarketPage"));
const MacroDashboardPage = lazy(() => import("./pages/MacroDashboardPage"));
const FundamentalsPage = lazy(() => import("./pages/FundamentalsPage"));
const WatchlistPage = lazy(() => import("./pages/WatchlistPage"));
const AIChatPage = lazy(() => import("./pages/AIChatPage"));
const MultiChartPage = lazy(() => import("./pages/MultiChartPage"));

function PageSkeleton() {
  return (
    <div style={{ padding: 16 }}>
      <div className="loading-skeleton">
        <div className="skeleton-line" style={{ height: 24, width: "40%", marginBottom: 16 }} />
        <div className="skeleton-line" />
        <div className="skeleton-line" />
        <div className="skeleton-line" />
        <div className="skeleton-line" style={{ width: "60%" }} />
      </div>
    </div>
  );
}

function AuthGuard({ children }) {
  const [authEnabled, setAuthEnabled] = useState(true);
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    let active = true;
    checkAuthStatus()
      .then((status) => {
        if (!active) return;
        setAuthEnabled(status?.auth_enabled !== false);
      })
      .catch(() => {
        if (!active) return;
        setAuthEnabled(true);
      })
      .finally(() => {
        if (active) setCheckingAuth(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (checkingAuth) {
    return <PageSkeleton />;
  }
  if (authEnabled && !isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <ToastProvider>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/*"
            element={
              <AuthGuard>
                <AppDataProvider>
                  <AppLayout>
                    <ErrorBoundary>
                      <Suspense fallback={<PageSkeleton />}>
                        <Routes>
                          <Route path="/" element={<DashboardPage />} />
                          <Route path="/kpis" element={<KPIDashboardPage />} />
                          <Route path="/ai-news" element={<AINewsPage />} />
                          <Route path="/live-market" element={<LiveMarketPage />} />
                          <Route path="/paper-trading" element={<PaperTradingPage />} />
                          <Route path="/backtest" element={<BacktestPage />} />
                          <Route path="/strategy-lab" element={<StrategyLabPage />} />
                          <Route path="/settings" element={<SettingsPage />} />
                          <Route path="/analyze" element={<AnalyzePage />} />
                          <Route path="/ranking" element={<RankingPage />} />
                          <Route path="/breadth" element={<BreadthPage />} />
                          <Route path="/risk" element={<RiskDashboardPage />} />
                          <Route path="/model-lab" element={<ModelLabPage />} />
                          <Route path="/alerts-center" element={<AlertsCenterPage />} />
                          <Route path="/trade-journal" element={<TradeJournalPage />} />
                          <Route path="/automation" element={<AutomationPage />} />
                          <Route path="/broker" element={<BrokerPage />} />
                          <Route path="/operations" element={<OperationsPage />} />
                          <Route path="/portfolio-exposure" element={<PortfolioExposurePage />} />
                          <Route path="/scan" element={<Navigate to="/ranking?mode=scan" replace />} />
                          <Route path="/ai-market" element={<AIMarketPage />} />
                          <Route path="/macro" element={<MacroDashboardPage />} />
                          <Route path="/fundamentals" element={<FundamentalsPage />} />
                          <Route path="/watchlist" element={<WatchlistPage />} />
                          <Route path="/ai-chat" element={<AIChatPage />} />
                          <Route path="/multi-chart" element={<MultiChartPage />} />
                          <Route path="/brain" element={<BrainDashboardPage />} />
                        </Routes>
                      </Suspense>
                    </ErrorBoundary>
                  </AppLayout>
                </AppDataProvider>
              </AuthGuard>
            }
          />
        </Routes>
      </Suspense>
    </ToastProvider>
  );
}
