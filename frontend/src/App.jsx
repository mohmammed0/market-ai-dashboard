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
const AINewsPage = lazy(() => import("./pages/AINewsPage"));
const LiveMarketPage = lazy(() => import("./pages/LiveMarketPage"));
const PaperTradingPage = lazy(() => import("./pages/PaperTradingPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const BrokerPage = lazy(() => import("./pages/BrokerPage"));
const AIMarketPage = lazy(() => import("./pages/AIMarketPage"));
const RankingPage = lazy(() => import("./pages/RankingPage"));

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
                          <Route path="/ai-news" element={<AINewsPage />} />
                          <Route path="/live-market" element={<LiveMarketPage />} />
                          <Route path="/paper-trading" element={<PaperTradingPage />} />
                          <Route path="/settings" element={<SettingsPage />} />
                          <Route path="/analyze" element={<Navigate to="/ai-market" replace />} />
                          <Route path="/ranking" element={<RankingPage />} />
                          <Route path="/broker" element={<BrokerPage />} />
                          <Route path="/scan" element={<Navigate to="/ranking?mode=scan" replace />} />
                          <Route path="/ai-market" element={<AIMarketPage />} />
                          <Route path="/kpis" element={<Navigate to="/" replace />} />
                          <Route path="/breadth" element={<Navigate to="/ranking" replace />} />
                          <Route path="/risk" element={<Navigate to="/broker" replace />} />
                          <Route path="/backtest" element={<Navigate to="/ranking" replace />} />
                          <Route path="/strategy-lab" element={<Navigate to="/ranking" replace />} />
                          <Route path="/model-lab" element={<Navigate to="/settings" replace />} />
                          <Route path="/alerts-center" element={<Navigate to="/paper-trading" replace />} />
                          <Route path="/trade-journal" element={<Navigate to="/paper-trading" replace />} />
                          <Route path="/automation" element={<Navigate to="/settings" replace />} />
                          <Route path="/operations" element={<Navigate to="/settings" replace />} />
                          <Route path="/portfolio-exposure" element={<Navigate to="/broker" replace />} />
                          <Route path="/macro" element={<Navigate to="/ai-market" replace />} />
                          <Route path="/fundamentals" element={<Navigate to="/ai-market" replace />} />
                          <Route path="/watchlist" element={<Navigate to="/ranking" replace />} />
                          <Route path="/ai-chat" element={<Navigate to="/ai-market" replace />} />
                          <Route path="/multi-chart" element={<Navigate to="/live-market" replace />} />
                          <Route path="/brain" element={<Navigate to="/settings" replace />} />
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
