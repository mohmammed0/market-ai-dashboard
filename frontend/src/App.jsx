import { Suspense, lazy } from "react";
import { Route, Routes, Navigate, useLocation } from "react-router-dom";
import AppShell from "./components/AppShell";
import LoadingSkeleton from "./components/ui/LoadingSkeleton";
import { isAuthenticated } from "./api/auth";
import ErrorBoundary from "./components/ui/ErrorBoundary";
import { ToastProvider } from "./components/ui/Toast";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const KPIDashboardPage = lazy(() => import("./pages/KPIDashboardPage"));
const AnalyzePage = lazy(() => import("./pages/AnalyzePage"));
const ScanPage = lazy(() => import("./pages/ScanPage"));
const RankingPage = lazy(() => import("./pages/RankingPage"));
const BacktestPage = lazy(() => import("./pages/BacktestPage"));
const RiskDashboardPage = lazy(() => import("./pages/RiskDashboardPage"));
const PortfolioExposurePage = lazy(() => import("./pages/PortfolioExposurePage"));
const ModelLabPage = lazy(() => import("./pages/ModelLabPage"));
const AINewsPage = lazy(() => import("./pages/AINewsPage"));
const LiveMarketPage = lazy(() => import("./pages/LiveMarketPage"));
const PaperTradingPage = lazy(() => import("./pages/PaperTradingPage"));
const AlertsCenterPage = lazy(() => import("./pages/AlertsCenterPage"));
const TradeJournalPage = lazy(() => import("./pages/TradeJournalPage"));
const StrategyLabPage = lazy(() => import("./pages/StrategyLabPage"));
const BreadthPage = lazy(() => import("./pages/BreadthPage"));
const AutomationPage = lazy(() => import("./pages/AutomationPage"));
const BrokerPage = lazy(() => import("./pages/BrokerPage"));
const OperationsPage = lazy(() => import("./pages/OperationsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

const navItems = [
  // Core - الأساسي
  { label: "مركز القيادة", path: "/", section: "الأساسي", meta: "Dashboard", priority: "primary" },
  { label: "مستكشف السوق", path: "/live-market", section: "الأساسي", meta: "Live Market", priority: "primary" },
  { label: "تحليل ذكي", path: "/analyze", section: "الأساسي", meta: "Analysis", priority: "primary" },
  { label: "الترتيب والفحص", path: "/ranking", section: "الأساسي", meta: "Ranking", priority: "primary" },
  { label: "التداول", path: "/paper-trading", section: "الأساسي", meta: "Trading", priority: "primary" },
  // Intelligence - الذكاء
  { label: "لوحات KPI", path: "/kpis", section: "التحليل", meta: "KPIs", priority: "primary" },
  { label: "اختبار تاريخي", path: "/backtest", section: "التحليل", meta: "Backtest", priority: "primary" },
  { label: "مختبر الاستراتيجية", path: "/strategy-lab", section: "التحليل", meta: "Strategy", priority: "secondary" },
  { label: "لوحة المخاطر", path: "/risk", section: "التحليل", meta: "Risk", priority: "secondary" },
  { label: "اتساع السوق", path: "/breadth", section: "التحليل", meta: "Breadth", priority: "secondary" },
  { label: "أخبار الذكاء", path: "/ai-news", section: "التحليل", meta: "AI News", priority: "secondary" },
  { label: "مختبر النماذج", path: "/model-lab", section: "التحليل", meta: "Models", priority: "secondary" },
  // System - النظام
  { label: "الإعدادات", path: "/settings", section: "النظام", meta: "Settings", priority: "primary" },
  { label: "العمليات", path: "/operations", section: "النظام", meta: "Operations", priority: "secondary" },
];

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
      <Suspense fallback={
        <div className="page-container">
          <div className="card" style={{ padding: "var(--space-8)" }}>
            <LoadingSkeleton lines={7} />
          </div>
        </div>
      }>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/*"
            element={
              <AuthGuard>
                <AppShell navItems={navItems}>
                  <ErrorBoundary>
                    <Suspense fallback={
                      <div className="page-container">
                        <div className="card" style={{ padding: "var(--space-8)" }}>
                          <LoadingSkeleton lines={7} />
                        </div>
                      </div>
                    }>
                      <Routes>
                        <Route path="/" element={<DashboardPage />} />
                        <Route path="/kpis" element={<KPIDashboardPage />} />
                        <Route path="/analyze" element={<AnalyzePage />} />
                        <Route path="/scan" element={<ScanPage />} />
                        <Route path="/ranking" element={<RankingPage />} />
                        <Route path="/breadth" element={<BreadthPage />} />
                        <Route path="/backtest" element={<BacktestPage />} />
                        <Route path="/strategy-lab" element={<StrategyLabPage />} />
                        <Route path="/risk" element={<RiskDashboardPage />} />
                        <Route path="/portfolio-exposure" element={<PortfolioExposurePage />} />
                        <Route path="/paper-trading" element={<PaperTradingPage />} />
                        <Route path="/broker" element={<BrokerPage />} />
                        <Route path="/alerts-center" element={<AlertsCenterPage />} />
                        <Route path="/trade-journal" element={<TradeJournalPage />} />
                        <Route path="/model-lab" element={<ModelLabPage />} />
                        <Route path="/ai-news" element={<AINewsPage />} />
                        <Route path="/live-market" element={<LiveMarketPage />} />
                        <Route path="/automation" element={<AutomationPage />} />
                        <Route path="/operations" element={<OperationsPage />} />
                        <Route path="/settings" element={<SettingsPage />} />
                      </Routes>
                    </Suspense>
                  </ErrorBoundary>
                </AppShell>
              </AuthGuard>
            }
          />
        </Routes>
      </Suspense>
    </ToastProvider>
  );
}
