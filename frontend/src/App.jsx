import { Suspense, lazy } from "react";
import { Route, Routes, Navigate, useLocation } from "react-router-dom";
import { isAuthenticated } from "./api/auth";
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
const ScanPage = lazy(() => import("./pages/ScanPage"));

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
  const location = useLocation();
  if (!isAuthenticated() && location.pathname !== "/login") {
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
                          <Route path="/scan" element={<ScanPage />} />
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
