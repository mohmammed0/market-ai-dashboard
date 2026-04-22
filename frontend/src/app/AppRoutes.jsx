import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "../components/layout/AppLayout";
import ErrorBoundary from "../components/ui/ErrorBoundary";
import { AppDataProvider } from "../store/AppDataStore";
import AuthGuard from "./AuthGuard";
import PageSkeleton from "./PageSkeleton";

const LoginPage = lazy(() => import("../pages/LoginPage"));
const DashboardPage = lazy(() => import("../pages/DashboardPage"));
const AINewsPage = lazy(() => import("../pages/AINewsPage"));
const LiveMarketPage = lazy(() => import("../pages/LiveMarketPage"));
const TradingDeskPage = lazy(() => import("../pages/TradingDeskPage"));
const SettingsPage = lazy(() => import("../pages/SettingsPage"));
const BrokerPage = lazy(() => import("../pages/BrokerPage"));
const AIMarketPage = lazy(() => import("../pages/AIMarketPage"));
const RankingPage = lazy(() => import("../pages/RankingPage"));
const KnowledgePage = lazy(() => import("../pages/KnowledgePage"));
const AutoTradingDiagnosticsPage = lazy(() => import("../pages/AutoTradingDiagnosticsPage"));

function ProtectedRoutes() {
  return (
    <AuthGuard>
      <AppDataProvider>
        <AppLayout>
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/ai-news" element={<AINewsPage />} />
                <Route path="/live-market" element={<LiveMarketPage />} />
                <Route path="/trading" element={<TradingDeskPage />} />
                <Route path="/paper-trading" element={<Navigate to="/trading" replace />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/analyze" element={<Navigate to="/ai-market" replace />} />
                <Route path="/ranking" element={<RankingPage />} />
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="/broker" element={<BrokerPage />} />
                <Route path="/scan" element={<Navigate to="/ranking?mode=scan" replace />} />
                <Route path="/ai-market" element={<AIMarketPage />} />
                <Route path="/kpis" element={<Navigate to="/" replace />} />
                <Route path="/breadth" element={<Navigate to="/ranking" replace />} />
                <Route path="/risk" element={<Navigate to="/broker" replace />} />
                <Route path="/backtest" element={<Navigate to="/ranking" replace />} />
                <Route path="/strategy-lab" element={<Navigate to="/ranking" replace />} />
                <Route path="/model-lab" element={<Navigate to="/settings" replace />} />
                <Route path="/alerts-center" element={<Navigate to="/trading" replace />} />
                <Route path="/trade-journal" element={<Navigate to="/trading" replace />} />
                <Route path="/diagnostics/auto-trading" element={<AutoTradingDiagnosticsPage />} />
                <Route path="/automation" element={<Navigate to="/settings" replace />} />
                <Route path="/operations" element={<Navigate to="/settings" replace />} />
                <Route path="/portfolio-exposure" element={<Navigate to="/broker" replace />} />
                <Route path="/macro" element={<Navigate to="/ai-market" replace />} />
                <Route path="/fundamentals" element={<Navigate to="/ai-market" replace />} />
                <Route path="/watchlist" element={<Navigate to="/ranking" replace />} />
                <Route path="/ai-chat" element={<Navigate to="/ai-market" replace />} />
                <Route path="/multi-chart" element={<Navigate to="/live-market" replace />} />
                <Route path="/brain" element={<AutoTradingDiagnosticsPage />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </AppLayout>
      </AppDataProvider>
    </AuthGuard>
  );
}

export default function AppRoutes() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<ProtectedRoutes />} />
      </Routes>
    </Suspense>
  );
}
