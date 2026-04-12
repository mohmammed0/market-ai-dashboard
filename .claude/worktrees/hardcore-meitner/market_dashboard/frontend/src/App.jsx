import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import LoadingSkeleton from "./components/ui/LoadingSkeleton";

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
  { label: "لوحة التداول", path: "/", section: "نظرة عامة", meta: "نظرة يومية", priority: "primary" },
  { label: "لوحات KPI", path: "/kpis", section: "نظرة عامة", meta: "ملخص الأداء", priority: "primary" },
  { label: "مستكشف السوق", path: "/live-market", section: "السوق", meta: "السوق المباشر", priority: "primary" },
  { label: "تحليل", path: "/analyze", section: "السوق", meta: "تحليل رمز", priority: "primary" },
  { label: "فحص", path: "/scan", section: "السوق", meta: "قوائم مرشحة", priority: "primary" },
  { label: "الترتيب", path: "/ranking", section: "السوق", meta: "أفضل الفرص", priority: "primary" },
  { label: "التداول التجريبي", path: "/paper-trading", section: "التداول", meta: "تنفيذ ورقي", priority: "primary" },
  { label: "مركز التنبيهات", path: "/alerts-center", section: "التداول", meta: "التنبيهات", priority: "primary" },
  { label: "انكشاف المحفظة", path: "/portfolio-exposure", section: "التداول", meta: "الانكشاف", priority: "primary" },
  { label: "لوحة المخاطر", path: "/risk", section: "التداول", meta: "الحماية", priority: "primary" },
  { label: "أخبار الذكاء", path: "/ai-news", section: "الذكاء", meta: "الأخبار", priority: "primary" },
  { label: "اتساع السوق", path: "/breadth", section: "الذكاء", meta: "السياق", priority: "primary" },
  { label: "مختبر الاستراتيجية", path: "/strategy-lab", section: "الذكاء", meta: "الاستراتيجيات", priority: "primary" },
  { label: "سجل التداول", path: "/trade-journal", section: "الذكاء", meta: "المراجعة", priority: "primary" },
  { label: "الأتمتة", path: "/automation", section: "الذكاء", meta: "المراقبة", priority: "primary" },
  { label: "اختبار تاريخي", path: "/backtest", section: "الذكاء", meta: "الاختبار", priority: "secondary" },
  { label: "مختبر النماذج", path: "/model-lab", section: "الذكاء", meta: "النماذج", priority: "secondary" },
  { label: "الوسيط", path: "/broker", section: "النظام", meta: "الوسيط", priority: "secondary" },
  { label: "العمليات", path: "/operations", section: "النظام", meta: "التشغيل", priority: "secondary" },
  { label: "الإعدادات", path: "/settings", section: "النظام", meta: "الإعدادات", priority: "primary" },
];

export default function App() {
  const routeFallback = (
    <div className="panel result-panel">
      <LoadingSkeleton lines={7} />
    </div>
  );

  return (
    <AppShell navItems={navItems}>
      <Suspense fallback={routeFallback}>
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
    </AppShell>
  );
}
