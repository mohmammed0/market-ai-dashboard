import { Suspense, lazy, useEffect, useState } from "react";
import { Route, Routes, Navigate } from "react-router-dom";
import { checkAuthStatus, isAuthenticated } from "./api/auth";
import ErrorBoundary from "./components/ui/ErrorBoundary";
import { ToastProvider } from "./components/ui/Toast";
import { AppDataProvider } from "./store/AppDataStore";
import AppLayout from "./components/layout/AppLayout";
import { CANONICAL_APP_ROUTES, LEGACY_ROUTE_ALIASES } from "./routes/routeAliases";

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
const KnowledgePage = lazy(() => import("./pages/KnowledgePage"));

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
                          <Route path={CANONICAL_APP_ROUTES.dashboard} element={<DashboardPage />} />
                          <Route path={CANONICAL_APP_ROUTES.aiNews} element={<AINewsPage />} />
                          <Route path={CANONICAL_APP_ROUTES.liveMarket} element={<LiveMarketPage />} />
                          <Route path={CANONICAL_APP_ROUTES.execution} element={<PaperTradingPage />} />
                          <Route path={CANONICAL_APP_ROUTES.settings} element={<SettingsPage />} />
                          <Route path={CANONICAL_APP_ROUTES.ranking} element={<RankingPage />} />
                          <Route path={CANONICAL_APP_ROUTES.knowledge} element={<KnowledgePage />} />
                          <Route path={CANONICAL_APP_ROUTES.broker} element={<BrokerPage />} />
                          <Route path={CANONICAL_APP_ROUTES.aiMarket} element={<AIMarketPage />} />
                          {LEGACY_ROUTE_ALIASES.map((alias) => (
                            <Route key={alias.from} path={alias.from} element={<Navigate to={alias.to} replace />} />
                          ))}
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
