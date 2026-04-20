import { useEffect, useMemo, useState } from "react";

import PageFrame from "../components/ui/PageFrame";
import SectionCard from "../components/ui/SectionCard";
import SummaryStrip from "../components/ui/SummaryStrip";
import DataTable from "../components/ui/DataTable";
import StatusBadge from "../components/ui/StatusBadge";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ErrorBanner from "../components/ui/ErrorBanner";
import {
  fetchAutoTradingDiagnosticsCycle,
  fetchAutoTradingDiagnosticsCycles,
  fetchKronosLatest,
  fetchAnalysisEnginesStatus,
  fetchKronosStatus,
  fetchMarketReadinessLatest,
  fetchMarketSessionStatus,
  getAutoTradingDiagnosticsExportUrl,
} from "../api/platform";


const REASON_CODE_META = {
  existing_long_position: {
    label: "مركز LONG موجود",
    detail: "تم منع فتح LONG جديد لأن هناك مركز LONG مفتوح بالفعل.",
    group: "existing_position",
  },
  existing_short_position: {
    label: "مركز SHORT موجود",
    detail: "تم منع فتح SHORT جديد لأن هناك مركز SHORT مفتوح بالفعل.",
    group: "existing_position",
  },
  insufficient_cash: {
    label: "سيولة غير كافية",
    detail: "التحقق النقدي منع الإرسال للوسيط.",
    group: "cash_margin",
  },
  insufficient_margin: {
    label: "هامش غير كافٍ",
    detail: "قواعد الهامش منعت فتح الصفقة.",
    group: "cash_margin",
  },
  risk_gate_blocked: {
    label: "محجوب بالمخاطر",
    detail: "بوابة المخاطر رفضت التنفيذ.",
    group: "risk_block",
  },
  market_closed: {
    label: "السوق مغلق",
    detail: "خارج الجلسة؛ لا يتم إرسال أمر للوسيط.",
    group: "market_session",
  },
  add_long_allowed: {
    label: "تم السماح بإضافة LONG",
    detail: "المنظومة سمحت بزيادة المركز القائم وفق السعة والاقتناع.",
    group: "submitted",
  },
  at_target_position_size: {
    label: "المركز عند الحجم المستهدف",
    detail: "لا توجد سعة إضافية للشراء لأن المركز وصل للحجم/النسبة المستهدفة.",
    group: "existing_position",
  },
  insufficient_add_conviction: {
    label: "اقتناع غير كافٍ للإضافة",
    detail: "قوة الإشارة/الدرجة أقل من الحد الأدنى للإضافة على مركز قائم.",
    group: "no_action",
  },
  add_cooldown_active: {
    label: "تبريد الإضافة فعّال",
    detail: "تم منع إضافة جديدة مؤقتًا لتقليل الإفراط في التداول.",
    group: "no_action",
  },
  add_blocked_by_cash: {
    label: "الإضافة محجوبة بالسيولة",
    detail: "لا توجد سيولة كافية للإضافة بالحجم المطلوب.",
    group: "cash_margin",
  },
  add_blocked_by_risk: {
    label: "الإضافة محجوبة بالمخاطر",
    detail: "قيود المخاطر منعت زيادة المركز الحالي.",
    group: "risk_block",
  },
  add_blocked_by_market_hours: {
    label: "الإضافة محجوبة بالجلسة",
    detail: "الجلسة/ساعات السوق منعت إرسال الإضافة.",
    group: "market_session",
  },
  add_qty_below_minimum: {
    label: "كمية الإضافة أقل من الحد الأدنى",
    detail: "الكمية/القيمة المحسوبة للإضافة لا تتجاوز الحد التشغيلي الأدنى.",
    group: "no_action",
  },
  existing_long_position_no_add: {
    label: "LONG قائم بدون إضافة",
    detail: "يوجد مركز LONG قائم لكن السياسة الحالية لم تسمح بإضافة جديدة.",
    group: "existing_position",
  },
  add_daily_limit_reached: {
    label: "وصل حد الإضافات اليومي",
    detail: "تم بلوغ الحد الأقصى لعدد إضافات LONG لهذا الرمز اليوم.",
    group: "no_action",
  },
  add_price_unavailable: {
    label: "سعر غير متاح للإضافة",
    detail: "لم تتوفر بيانات سعر موثوقة لحساب كمية الإضافة.",
    group: "no_action",
  },
  skipped_lower_rank: {
    label: "تخطي بسبب ترتيب أدنى",
    detail: "تم توجيه رأس المال لفرص أعلى ترتيبًا.",
    group: "no_action",
  },
  skipped_cash_reserved: {
    label: "تخطي بسبب احتياطي نقدي",
    detail: "المنظومة حفظت سيولة احتياطية بدل تمويل هذه الفرصة.",
    group: "cash_margin",
  },
  skipped_due_to_better_existing_use: {
    label: "تخطي بسبب استخدام أفضل لرأس المال",
    detail: "مركز/فرصة أخرى اعتُبرت أفضل استخدامًا لرأس المال المتاح.",
    group: "no_action",
  },
  skipped_due_to_concentration: {
    label: "تخطي بسبب التركيز",
    detail: "سياسة التركيز منعت تمويل الصفقة.",
    group: "risk_block",
  },
  skipped_due_to_regime: {
    label: "تخطي بسبب نظام السوق",
    detail: "حالة السوق الحالية لا تسمح بهذا النوع من التخصيص.",
    group: "market_session",
  },
  reduce_due_to_better_use_of_capital: {
    label: "خفض لصالح استخدام أفضل لرأس المال",
    detail: "تم تخفيض مركز قائم لصالح فرصة أعلى جودة.",
    group: "existing_position",
  },
  exit_due_to_replacement: {
    label: "خروج بسبب استبدال",
    detail: "تم إغلاق مركز قائم لإفساح رأس المال لفرصة أقوى.",
    group: "existing_position",
  },
  duplicate_intent_suppressed: {
    label: "نية مكررة",
    detail: "تم كتم النية المتكررة لحماية التنفيذ.",
    group: "no_action",
  },
  no_action_from_signal: {
    label: "لا توجد حركة",
    detail: "الإشارة لا تنتج إجراء تداول فعلي.",
    group: "no_action",
  },
  order_rejected: {
    label: "رفض من الوسيط",
    detail: "الوسيط رفض الطلب.",
    group: "broker_rejection",
  },
  broker_rejected: {
    label: "رفض من الوسيط",
    detail: "الوسيط رفض الطلب.",
    group: "broker_rejection",
  },
  broker_not_called: {
    label: "لم يتم استدعاء الوسيط",
    detail: "لم تُنفذ محاولة إرسال للوسيط لهذه الحالة.",
    group: "no_action",
  },
  order_submitted: {
    label: "تم الإرسال",
    detail: "تم إرسال الطلب إلى الوسيط.",
    group: "submitted",
  },
  order_accepted: {
    label: "قبول الوسيط",
    detail: "الوسيط قبل الطلب.",
    group: "submitted",
  },
  order_pending: {
    label: "معلق لدى الوسيط",
    detail: "الطلب ما زال قيد المتابعة لدى الوسيط.",
    group: "submitted",
  },
  order_filled: {
    label: "تم التنفيذ",
    detail: "الطلب تم تنفيذه بالكامل.",
    group: "submitted",
  },
  order_partially_filled: {
    label: "تنفيذ جزئي",
    detail: "الطلب تم تنفيذه جزئيًا.",
    group: "submitted",
  },
  order_cancelled: {
    label: "تم الإلغاء",
    detail: "الطلب أُلغي.",
    group: "submitted",
  },
};

const REASON_GROUP_META = {
  existing_position: { label: "مركز قائم", tone: "warning" },
  risk_block: { label: "حجب مخاطر", tone: "negative" },
  cash_margin: { label: "سيولة/هامش", tone: "negative" },
  market_session: { label: "جلسة السوق", tone: "warning" },
  broker_rejection: { label: "رفض الوسيط", tone: "negative" },
  no_action: { label: "لا إجراء", tone: "neutral" },
  submitted: { label: "مرسل للوسيط", tone: "positive" },
  unknown: { label: "غير مصنف", tone: "neutral" },
};

const BLOCKED_REASON_CODES = new Set([
  "existing_long_position",
  "existing_short_position",
  "existing_long_position_no_add",
  "at_target_position_size",
  "insufficient_cash",
  "insufficient_margin",
  "risk_gate_blocked",
  "add_blocked_by_risk",
  "add_blocked_by_cash",
  "add_blocked_by_market_hours",
  "add_cooldown_active",
  "add_daily_limit_reached",
  "insufficient_add_conviction",
  "add_qty_below_minimum",
  "market_closed",
  "duplicate_intent_suppressed",
  "order_rejected",
  "broker_rejected",
]);


function toneForSignal(signal) {
  const normalized = String(signal || "").toUpperCase();
  if (normalized === "BUY") return "positive";
  if (normalized === "SELL") return "negative";
  return "neutral";
}


function toneForGuardrail(result) {
  const normalized = String(result || "").toLowerCase();
  if (normalized === "passed") return "positive";
  if (normalized === "blocked") return "negative";
  if (normalized === "not_checked") return "warning";
  return "neutral";
}


function toneForComponentContribution(contributed, ready) {
  if (contributed) return "positive";
  if (ready) return "warning";
  return "neutral";
}

function toneForOutcome(code) {
  const normalized = String(code || "").toLowerCase();
  if (normalized.includes("filled") || normalized.includes("accepted") || normalized.includes("submitted")) return "positive";
  if (normalized.includes("rejected") || normalized.includes("insufficient") || normalized.includes("blocked")) return "negative";
  if (
    normalized.includes("existing") ||
    normalized.includes("no_action") ||
    normalized.includes("market_closed") ||
    normalized.includes("at_target") ||
    normalized.includes("cooldown")
  ) {
    return "warning";
  }
  return "neutral";
}


function toneForFundingStatus(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized.includes("full")) return "positive";
  if (normalized.includes("partial")) return "warning";
  if (normalized.includes("not_applicable")) return "info";
  if (normalized.includes("unfunded")) return "negative";
  return "neutral";
}

function toneForPriorityBand(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical") return "negative";
  if (normalized === "high") return "warning";
  if (normalized === "normal") return "info";
  if (normalized === "low") return "neutral";
  if (normalized === "deferred") return "neutral";
  return "neutral";
}

function toneForQueueStatus(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "submitted") return "positive";
  if (normalized === "ready") return "info";
  if (normalized === "waiting_for_prerequisite") return "warning";
  if (normalized === "deferred") return "warning";
  if (normalized === "skipped" || normalized === "cancelled") return "neutral";
  return "neutral";
}

function toneForQueueGate(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "go") return "positive";
  if (normalized === "defer") return "warning";
  if (normalized === "wait") return "warning";
  if (normalized === "skip") return "neutral";
  return "neutral";
}

function toneForExecutionEngineStatus(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "submitted_to_execution_engine") return "positive";
  if (normalized === "ready") return "info";
  if (normalized === "waiting_for_dependency") return "warning";
  if (normalized === "retry_scheduled" || normalized === "backoff_active") return "warning";
  if (normalized === "deferred") return "warning";
  if (normalized === "skipped" || normalized === "cancelled") return "neutral";
  return "neutral";
}

function toneForBrokerSubmissionStatus(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "broker_submitted") return "positive";
  if (normalized === "broker_submission_pending") return "warning";
  if (normalized === "not_attempted") return "neutral";
  return "neutral";
}

function toneForReconciliation(row) {
  if (row?.reconciliation_window_expired) return "warning";
  if (row?.reconciliation_terminal) return "positive";
  if (row?.reconciliation_started_at && !row?.reconciliation_completed_at) return "info";
  if (row?.reconciliation_started_at) return "positive";
  return "neutral";
}

function reasonCodeForRow(row) {
  return String(
    row?.why_no_broker_order_code ||
      row?.final_outcome_code ||
      row?.guardrail_reason_code ||
      "unknown"
  ).toLowerCase();
}


function reasonMetaForRow(row) {
  const code = reasonCodeForRow(row);
  const found = REASON_CODE_META[code];
  if (found) {
    return { code, ...found };
  }
  return {
    code,
    label: code || "unknown",
    detail: row?.why_no_broker_order_detail || row?.final_outcome_detail || "-",
    group: "unknown",
  };
}


function groupMeta(group) {
  return REASON_GROUP_META[group] || REASON_GROUP_META.unknown;
}


function whyNoBrokerBadge(row) {
  if (row?.broker_order_submitted) {
    return {
      label: "تم الإرسال",
      detail: "Broker order submitted",
      tone: "positive",
    };
  }
  const meta = reasonMetaForRow(row);
  return {
    label: meta.label,
    detail: meta.detail,
    tone: groupMeta(meta.group).tone,
  };
}


function brokerStatusDisplay(row) {
  if (!row?.broker_order_submitted) {
    const skipReason = String(row?.execution_skip_reason || row?.broker_skip_reason || "").trim();
    return {
      label: skipReason ? `No broker call (${skipReason})` : "No broker call this cycle",
      tone: "neutral",
    };
  }
  return {
    label: row?.execution_outcome_code || row?.broker_outcome_code || row?.broker_order_status || "submitted",
    tone: toneForOutcome(row?.execution_outcome_code || row?.broker_outcome_code || row?.broker_order_status),
  };
}


export default function AutoTradingDiagnosticsPage() {
  const [cyclesLoading, setCyclesLoading] = useState(true);
  const [cyclesError, setCyclesError] = useState("");
  const [cycles, setCycles] = useState([]);
  const [selectedCycleId, setSelectedCycleId] = useState("");

  const [cycleLoading, setCycleLoading] = useState(false);
  const [cycleError, setCycleError] = useState("");
  const [cycle, setCycle] = useState(null);

  const [detailRowsBySymbol, setDetailRowsBySymbol] = useState({});
  const [detailLoadingSymbol, setDetailLoadingSymbol] = useState("");
  const [marketSessionSnapshot, setMarketSessionSnapshot] = useState(null);
  const [marketReadinessSnapshot, setMarketReadinessSnapshot] = useState(null);
  const [kronosRuntimeSnapshot, setKronosRuntimeSnapshot] = useState(null);
  const [kronosLatestSnapshot, setKronosLatestSnapshot] = useState(null);
  const [analysisEnginesSnapshot, setAnalysisEnginesSnapshot] = useState(null);

  const [blockedOnly, setBlockedOnly] = useState(false);
  const [submittedOnly, setSubmittedOnly] = useState(false);
  const [existingPositionOnly, setExistingPositionOnly] = useState(false);
  const [marketClosedOnly, setMarketClosedOnly] = useState(false);
  const [riskBlockedOnly, setRiskBlockedOnly] = useState(false);
  const [brokerRejectedOnly, setBrokerRejectedOnly] = useState(false);
  const [reasonCode, setReasonCode] = useState("");
  const [actionType, setActionType] = useState("");
  const [fundingStatus, setFundingStatus] = useState("");
  const [priorityBand, setPriorityBand] = useState("");
  const [queueStatus, setQueueStatus] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState("");

  async function loadCycles() {
    setCyclesLoading(true);
    setCyclesError("");
    try {
      const payload = await fetchAutoTradingDiagnosticsCycles({ limit: 20, includeRows: false });
      const items = payload?.items || [];
      setCycles(items);
      if (!selectedCycleId && items.length) {
        const firstWithRows = items.find((item) => Number(item?.rows_count || 0) > 0);
        setSelectedCycleId((firstWithRows || items[0]).cycle_id);
      }
    } catch (error) {
      setCyclesError(error.message || "تعذر تحميل دورات التشخيص.");
    } finally {
      setCyclesLoading(false);
    }
  }

  async function loadCycle(cycleId) {
    if (!cycleId) {
      setCycle(null);
      return;
    }
    setCycleLoading(true);
    setCycleError("");
    setDetailRowsBySymbol({});
    setDetailLoadingSymbol("");
    try {
      const payload = await fetchAutoTradingDiagnosticsCycle(cycleId, {
        includeDetails: false,
        includeModelBreakdown: false,
        includeRaw: false,
      });
      const item = payload?.item || null;
      setCycle(item);
      const firstSymbol = item?.rows?.[0]?.symbol || "";
      setSelectedSymbol(firstSymbol);
    } catch (error) {
      setCycleError(error.message || "تعذر تحميل تفاصيل الدورة.");
      setCycle(null);
    } finally {
      setCycleLoading(false);
    }
  }

  async function loadIntelligenceStatus() {
    try {
      const [sessionPayload, readinessPayload, kronosStatusPayload, kronosLatestPayload, analysisEnginesPayload] = await Promise.all([
        fetchMarketSessionStatus({ refresh: false }),
        fetchMarketReadinessLatest(),
        fetchKronosStatus(),
        fetchKronosLatest({ limitSymbols: 12 }),
        fetchAnalysisEnginesStatus({ latestNonempty: true }),
      ]);
      setMarketSessionSnapshot(sessionPayload?.item || null);
      setMarketReadinessSnapshot(readinessPayload?.item || null);
      setKronosRuntimeSnapshot(kronosStatusPayload?.item || null);
      setKronosLatestSnapshot(kronosLatestPayload?.item || null);
      setAnalysisEnginesSnapshot(analysisEnginesPayload?.item || null);
    } catch {
      // Non-blocking intelligence widgets.
    }
  }

  async function loadSymbolDetail(symbol) {
    if (!selectedCycleId || !symbol) return;
    if (detailRowsBySymbol[symbol]) return;
    setDetailLoadingSymbol(symbol);
    try {
      const payload = await fetchAutoTradingDiagnosticsCycle(selectedCycleId, {
        includeDetails: true,
        includeModelBreakdown: true,
        includeRaw: true,
        rowSymbol: symbol,
      });
      const row = payload?.item?.rows?.[0] || null;
      if (row) {
        setDetailRowsBySymbol((prev) => ({ ...prev, [symbol]: row }));
      }
    } catch {
      // Keep UI responsive; detail fetch errors should not break table browsing.
    } finally {
      setDetailLoadingSymbol("");
    }
  }

  useEffect(() => {
    loadCycles().catch(() => {});
    loadIntelligenceStatus().catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedCycleId) return;
    loadCycle(selectedCycleId).catch(() => {});
    loadIntelligenceStatus().catch(() => {});
  }, [selectedCycleId]);

  useEffect(() => {
    if (!selectedSymbol) return;
    loadSymbolDetail(selectedSymbol).catch(() => {});
  }, [selectedSymbol, selectedCycleId]);

  const rows = useMemo(() => {
    return Array.isArray(cycle?.rows) ? cycle.rows : [];
  }, [cycle]);

  const reasonCodes = useMemo(() => {
    const values = new Set();
    for (const row of rows) {
      values.add(reasonCodeForRow(row));
      if (row?.final_outcome_code) values.add(String(row.final_outcome_code).toLowerCase());
      if (row?.guardrail_reason_code) values.add(String(row.guardrail_reason_code).toLowerCase());
    }
    return Array.from(values).filter(Boolean).sort();
  }, [rows]);

  const actionTypes = useMemo(() => {
    const values = new Set();
    for (const row of rows) {
      if (row?.requested_execution_action) values.add(String(row.requested_execution_action));
      if (row?.actual_execution_action) values.add(String(row.actual_execution_action));
      if (row?.final_execution_action) values.add(String(row.final_execution_action));
      if (row?.derived_intent) values.add(String(row.derived_intent));
    }
    return Array.from(values).sort();
  }, [rows]);

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const finalCode = String(row?.final_outcome_code || "").toLowerCase();
      const guardrailCode = String(row?.guardrail_reason_code || "").toLowerCase();
      const rowReason = reasonCodeForRow(row);
      const reasonMeta = reasonMetaForRow(row);

      if (blockedOnly) {
        const blocked =
          String(row?.guardrail_result || "").toLowerCase() === "blocked" ||
          BLOCKED_REASON_CODES.has(finalCode) ||
          BLOCKED_REASON_CODES.has(rowReason);
        if (!blocked) return false;
      }
      if (submittedOnly && !row?.broker_order_submitted) return false;
      if (existingPositionOnly && reasonMeta.group !== "existing_position") return false;
      if (
        marketClosedOnly &&
        finalCode !== "market_closed" &&
        finalCode !== "add_blocked_by_market_hours" &&
        rowReason !== "market_closed" &&
        rowReason !== "add_blocked_by_market_hours"
      ) {
        return false;
      }
      if (
        riskBlockedOnly &&
        finalCode !== "risk_gate_blocked" &&
        finalCode !== "add_blocked_by_risk" &&
        guardrailCode !== "risk_gate_blocked" &&
        guardrailCode !== "add_blocked_by_risk"
      ) {
        return false;
      }
      if (brokerRejectedOnly && !["order_rejected", "broker_rejected"].includes(finalCode)) return false;
      if (reasonCode && rowReason !== reasonCode && finalCode !== reasonCode && guardrailCode !== reasonCode) return false;
      if (fundingStatus) {
        const normalizedFunding = String(row?.funding_status || "").toLowerCase();
        if (fundingStatus === "full" && !normalizedFunding.includes("full")) return false;
        if (fundingStatus === "partial" && !normalizedFunding.includes("partial")) return false;
        if (fundingStatus === "unfunded" && !normalizedFunding.includes("unfunded")) return false;
      }
      if (priorityBand && String(row?.execution_priority_band || "").toLowerCase() !== priorityBand.toLowerCase()) return false;
      if (queueStatus && String(row?.queue_status || "").toLowerCase() !== queueStatus.toLowerCase()) return false;
      if (
        actionType &&
        String(row?.requested_execution_action || "") !== actionType &&
        String(row?.actual_execution_action || "") !== actionType &&
        String(row?.final_execution_action || "") !== actionType &&
        String(row?.derived_intent || "") !== actionType
      ) {
        return false;
      }
      return true;
    });
  }, [
    rows,
    blockedOnly,
    submittedOnly,
    existingPositionOnly,
    marketClosedOnly,
    riskBlockedOnly,
    brokerRejectedOnly,
    reasonCode,
    fundingStatus,
    priorityBand,
    queueStatus,
    actionType,
  ]);

  const reasonGroupCounts = useMemo(() => {
    const counts = {};
    for (const row of rows) {
      const group = reasonMetaForRow(row).group;
      counts[group] = (counts[group] || 0) + 1;
    }
    return counts;
  }, [rows]);

  const summaryCounts = cycle?.summary_counts || {};
  const signalSummaryItems = [
    { label: "BUY Signals", value: summaryCounts.signal_buy_count ?? 0, tone: "positive" },
    { label: "SELL Signals", value: summaryCounts.signal_sell_count ?? 0, tone: "negative" },
    { label: "HOLD Signals", value: summaryCounts.signal_hold_count ?? 0, tone: "neutral" },
  ];
  const executionSummaryItems = [
    { label: "Submitted", value: summaryCounts.submitted_order_count ?? 0, tone: "info" },
    { label: "Accepted", value: summaryCounts.accepted_order_count ?? 0, tone: "positive" },
    { label: "Rejected", value: summaryCounts.rejected_order_count ?? 0, tone: "negative" },
    { label: "Filled", value: summaryCounts.filled_order_count ?? 0, tone: "positive" },
    { label: "Partial Fill", value: summaryCounts.partially_filled_order_count ?? 0, tone: "warning" },
    { label: "Blocked", value: summaryCounts.blocked_count ?? 0, tone: "warning" },
    { label: "No Action", value: summaryCounts.no_action_count ?? 0, tone: "neutral" },
  ];

  const marketSession = cycle?.market_session || marketSessionSnapshot || {};
  const marketReadiness =
    cycle?.market_readiness ||
    (marketReadinessSnapshot?.market_readiness ? marketReadinessSnapshot.market_readiness : marketReadinessSnapshot) ||
    {};
  const kronosCycle = cycle?.kronos || {};
  const kronosStatus = kronosCycle?.status || kronosRuntimeSnapshot || {};
  const kronosBatchSummary = kronosCycle?.batch_summary || marketReadiness?.kronos || {};
  const kronosRowsFromCycle = rows
    .filter((row) => row?.kronos_ready || Number(row?.kronos_score || 0) > 0)
    .sort((a, b) => Number(b?.kronos_score || 0) - Number(a?.kronos_score || 0))
    .slice(0, 8);
  const kronosRowsFromApi = Array.isArray(kronosLatestSnapshot?.symbols)
    ? kronosLatestSnapshot.symbols.slice(0, 8)
    : [];
  const kronosTopSymbols = kronosRowsFromCycle.length ? kronosRowsFromCycle : kronosRowsFromApi;

  const analysisEnginesStatus = analysisEnginesSnapshot || {};
  const analysisEngineUsage = analysisEnginesStatus?.latest_cycle || cycle?.analysis_engines || {};
  const readinessPassedCount = Array.isArray(marketReadiness?.readiness_checks_passed)
    ? marketReadiness.readiness_checks_passed.length
    : Number(marketReadiness?.readiness_checks_passed || 0);
  const readinessFailedCount = Array.isArray(marketReadiness?.readiness_checks_failed)
    ? marketReadiness.readiness_checks_failed.length
    : Number(marketReadiness?.readiness_checks_failed || 0);
  const deskBrief = marketReadiness?.desk_brief || {};
  const premarketCandidates = Array.isArray(marketReadiness?.premarket_candidates) ? marketReadiness.premarket_candidates : [];
  const queuedForOpenCandidates = Array.isArray(marketReadiness?.queued_for_open_candidates) ? marketReadiness.queued_for_open_candidates : [];
  const waitForOpenCandidates = Array.isArray(marketReadiness?.wait_for_open_confirmation_candidates)
    ? marketReadiness.wait_for_open_confirmation_candidates
    : [];
  const preopenReduceCandidates = Array.isArray(marketReadiness?.preopen_reduce_candidates) ? marketReadiness.preopen_reduce_candidates : [];
  const deskBriefRiskFlags = deskBrief?.top_risk_flags && typeof deskBrief.top_risk_flags === "object"
    ? Object.entries(deskBrief.top_risk_flags)
    : [];
  const analysisEngineSummaryItems = [
    {
      label: "Classic",
      value: `${analysisEnginesStatus?.classic?.ready ? "READY" : "OFF"} | used ${Number(analysisEngineUsage?.classic_used_count ?? summaryCounts.classic_used_count ?? 0)}`,
      tone: analysisEnginesStatus?.classic?.ready ? "positive" : "warning",
    },
    {
      label: "Ranking",
      value: `${analysisEnginesStatus?.ranking?.ready ? "READY" : "OFF"} | used ${Number(analysisEngineUsage?.ranking_used_count ?? summaryCounts.ranking_used_count ?? 0)}`,
      tone: analysisEnginesStatus?.ranking?.ready ? "positive" : "warning",
    },
    {
      label: "ML",
      value: `${analysisEnginesStatus?.ml?.ready ? "READY" : "DEGRADED"} | used ${Number(analysisEngineUsage?.ml_used_count ?? summaryCounts.ml_used_count ?? 0)}`,
      tone: analysisEnginesStatus?.ml?.ready ? "positive" : "warning",
    },
    {
      label: "DL",
      value: `${analysisEnginesStatus?.dl?.ready ? "READY" : "DEGRADED"} | used ${Number(analysisEngineUsage?.dl_used_count ?? summaryCounts.dl_used_count ?? 0)}`,
      tone: analysisEnginesStatus?.dl?.ready ? "positive" : "warning",
    },
    {
      label: "Kronos",
      value: `${analysisEnginesStatus?.kronos?.ready ? "READY" : "DEGRADED"} | used ${Number(analysisEngineUsage?.kronos_used_count ?? summaryCounts.kronos_used_count ?? 0)}`,
      tone: analysisEnginesStatus?.kronos?.ready ? "positive" : "warning",
    },
  ];

  const regime = cycle?.regime || {};
  const marketJudgment = cycle?.market_judgment || marketReadiness?.market_judgment || {};
  const portfolioSleeves = cycle?.portfolio_sleeves || marketReadiness?.portfolio_sleeves || {};
  const selfGovernedLimits = cycle?.self_governed_limits || marketReadiness?.self_governed_limits || {};
  const judgmentSummary = cycle?.judgment_summary || marketReadiness?.judgment_summary || {};
  const allocationSummary = cycle?.allocation_summary || {};
  const allocationLedger = cycle?.allocation_ledger || {};
  const selfReview = cycle?.self_review || {};
  const dailyReview = selfReview?.daily_review || {};
  const weeklyReview = selfReview?.weekly_review || {};
  const executionQueueSummary = cycle?.execution_queue_summary || {};
  const executionQueue = Array.isArray(cycle?.execution_queue) ? cycle.execution_queue : [];
  const executionTimeline = Array.isArray(cycle?.execution_timeline) ? cycle.execution_timeline : [];

  const sessionSummaryItems = [
    { label: "Session", value: marketSession?.session_state || marketSession?.session_code || "-", tone: "info" },
    { label: "Market Open", value: marketSession?.market_open ? "YES" : "NO", tone: marketSession?.market_open ? "positive" : "warning" },
    { label: "Trading Day", value: marketSession?.is_trading_day ? "YES" : "NO", tone: marketSession?.is_trading_day ? "positive" : "neutral" },
    { label: "Minutes To Open", value: Number(marketSession?.minutes_to_open ?? 0), tone: "neutral" },
    { label: "Minutes To Close", value: Number(marketSession?.minutes_to_close ?? 0), tone: "neutral" },
    { label: "Extended Hours", value: marketSession?.extended_hours_available ? "YES" : "NO", tone: marketSession?.extended_hours_available ? "positive" : "neutral" },
  ];

  const readinessSummaryItems = [
    { label: "Readiness %", value: Number(marketReadiness?.readiness_completed_percent || 0).toFixed(1), tone: "info" },
    { label: "Checks Passed", value: readinessPassedCount, tone: "positive" },
    { label: "Checks Failed", value: readinessFailedCount, tone: readinessFailedCount > 0 ? "warning" : "neutral" },
    { label: "Ready For Open", value: marketReadiness?.ready_for_open ? "YES" : "NO", tone: marketReadiness?.ready_for_open ? "positive" : "warning" },
    { label: "Pre-market Candidates", value: Number(marketReadiness?.premarket_candidate_count || 0), tone: "info" },
    { label: "Queued For Open", value: Number(marketReadiness?.queued_for_open_count || 0), tone: "warning" },
  ];

  const kronosSummaryItems = [
    { label: "Kronos Enabled", value: kronosStatus?.kronos_enabled ? "YES" : "NO", tone: kronosStatus?.kronos_enabled ? "positive" : "neutral" },
    { label: "Kronos Loaded", value: kronosStatus?.kronos_loaded ? "YES" : "NO", tone: kronosStatus?.kronos_loaded ? "positive" : "warning" },
    { label: "Kronos Warmed", value: kronosStatus?.kronos_warmed ? "YES" : "NO", tone: kronosStatus?.kronos_warmed ? "positive" : "warning" },
    { label: "Batch Ready", value: Number(kronosBatchSummary?.kronos_batch_ready_count || 0), tone: "info" },
    { label: "Batch Symbols", value: Number(kronosBatchSummary?.kronos_batch_symbol_count || 0), tone: "neutral" },
    { label: "Batch Duration ms", value: Number(kronosBatchSummary?.kronos_batch_duration_ms || 0).toFixed(1), tone: "neutral" },
  ];

  const regimeSummaryItems = [
    { label: "Regime", value: regime.regime_code || "-", tone: toneForOutcome(regime.regime_bias || regime.regime_code) },
    { label: "Bias", value: regime.regime_bias || "-", tone: toneForOutcome(regime.regime_bias) },
    { label: "Confidence", value: Number(regime.regime_confidence || 0).toFixed(1), tone: "info" },
    { label: "Risk Mult", value: Number(regime.risk_multiplier || 0).toFixed(2), tone: "warning" },
    { label: "Max New", value: regime.max_new_positions ?? 0, tone: "neutral" },
    { label: "Add Allowed", value: regime.add_allowed ? "YES" : "NO", tone: regime.add_allowed ? "positive" : "warning" },
  ];

  const marketJudgmentItems = [
    { label: "Session", value: marketJudgment.session_state || "-", tone: "info" },
    { label: "Market Quality", value: Number(marketJudgment.market_quality_score || 0).toFixed(1), tone: Number(marketJudgment.market_quality_score || 0) >= 60 ? "positive" : Number(marketJudgment.market_quality_score || 0) >= 50 ? "warning" : "negative" },
    { label: "Offense", value: Number(marketJudgment.market_offense_level || 0).toFixed(1), tone: "positive" },
    { label: "Defense", value: Number(marketJudgment.market_defense_level || 0).toFixed(1), tone: "warning" },
    { label: "Cash Preference", value: Number(marketJudgment.market_cash_preference || 0).toFixed(1), tone: "neutral" },
    { label: "Small Caps", value: marketJudgment.tactical_small_caps_allowed ? "ALLOWED" : "OFF", tone: marketJudgment.tactical_small_caps_allowed ? "positive" : "warning" },
    { label: "Pre-market", value: marketJudgment.premarket_participation_allowed ? "ALLOWED" : "OFF", tone: marketJudgment.premarket_participation_allowed ? "positive" : "warning" },
    { label: "Open Handoff", value: marketJudgment.open_handoff_readiness ? "READY" : "PENDING", tone: marketJudgment.open_handoff_readiness ? "positive" : "warning" },
  ];

  const portfolioActionItems = [
    { label: "OPEN_LONG", value: summaryCounts.derived_open_long_count ?? 0, tone: "positive" },
    { label: "ADD_LONG", value: summaryCounts.derived_add_long_count ?? 0, tone: "positive" },
    { label: "REDUCE_LONG", value: summaryCounts.derived_reduce_long_count ?? 0, tone: "warning" },
    { label: "EXIT_LONG", value: summaryCounts.derived_exit_long_count ?? 0, tone: "negative" },
    { label: "HOLD", value: summaryCounts.derived_hold_count ?? 0, tone: "neutral" },
  ];

  const queueSummaryItems = [
    { label: "Queued", value: executionQueueSummary.queue_total ?? executionQueue.length, tone: "info" },
    { label: "Submitted", value: executionQueueSummary.submitted_count ?? 0, tone: "positive" },
    { label: "Waiting", value: executionQueueSummary.waiting_count ?? 0, tone: "warning" },
    { label: "Deferred", value: executionQueueSummary.deferred_count ?? 0, tone: "warning" },
    { label: "Skipped", value: executionQueueSummary.skipped_count ?? 0, tone: "neutral" },
    { label: "Retry Scheduled", value: executionQueueSummary.retry_scheduled_count ?? 0, tone: "warning" },
    { label: "Backoff Active", value: executionQueueSummary.backoff_active_count ?? 0, tone: "warning" },
    { label: "Re-sized", value: executionQueueSummary.resized_after_execution_result_count ?? 0, tone: "info" },
    { label: "Recon Active", value: executionQueueSummary.reconciliation_active_count ?? 0, tone: "info" },
    { label: "Recon Done", value: executionQueueSummary.reconciliation_completed_count ?? 0, tone: "positive" },
    { label: "Recon Polls", value: executionQueueSummary.reconciliation_poll_count_total ?? 0, tone: "neutral" },
  ];

  const submittedQueue = Array.isArray(executionQueueSummary?.submitted_order_sequence)
    ? executionQueueSummary.submitted_order_sequence
    : executionQueue.filter((item) => String(item?.queue_status || "") === "submitted");
  const deferredQueue = Array.isArray(executionQueueSummary?.deferred_order_sequence)
    ? executionQueueSummary.deferred_order_sequence
    : executionQueue.filter((item) => String(item?.queue_status || "") === "deferred");
  const skippedQueue = Array.isArray(executionQueueSummary?.skipped_order_sequence)
    ? executionQueueSummary.skipped_order_sequence
    : executionQueue.filter((item) => String(item?.queue_status || "") === "skipped");
  const waitingQueue = executionQueue.filter((item) => String(item?.queue_status || "") === "waiting_for_prerequisite");

  const highestUnfunded = Array.isArray(allocationSummary?.highest_unfunded) ? allocationSummary.highest_unfunded : [];
  const sleeveTargets = portfolioSleeves?.sleeve_targets || {};
  const sleeveActuals = portfolioSleeves?.sleeve_actuals || {};
  const sleeveRows = Object.keys({ ...sleeveTargets, ...sleeveActuals }).map((key) => ({
    sleeve: key,
    target: Number(sleeveTargets?.[key] || 0).toFixed(1),
    actual: Number(sleeveActuals?.[key] || 0).toFixed(1),
  }));
  const rotationOpportunities = Array.isArray(judgmentSummary?.rotation_opportunities) ? judgmentSummary.rotation_opportunities : [];
  const whyNotBuying = Array.isArray(judgmentSummary?.why_not_buying) ? judgmentSummary.why_not_buying : [];
  const smallCapCandidates = Array.isArray(judgmentSummary?.small_cap_tactical_candidates) ? judgmentSummary.small_cap_tactical_candidates : [];

  const selectedRow = useMemo(() => {
    if (!selectedSymbol) return null;
    const baseRow = filteredRows.find((row) => row.symbol === selectedSymbol) || rows.find((row) => row.symbol === selectedSymbol) || null;
    if (!baseRow) return null;
    const detailed = detailRowsBySymbol[selectedSymbol];
    return detailed ? { ...baseRow, ...detailed } : baseRow;
  }, [selectedSymbol, filteredRows, rows, detailRowsBySymbol]);

  const columns = useMemo(
    () => [
      {
        accessorKey: "symbol",
        header: "الرمز",
        cell: ({ row }) => (
          <button
            type="button"
            className="btn btn-secondary btn-xs"
            onClick={() => setSelectedSymbol(row.original.symbol)}
          >
            {row.original.symbol}
          </button>
        ),
      },
      {
        accessorKey: "analysis_signal",
        header: "Signal",
        cell: ({ row }) => (
          <StatusBadge
            label={row.original.analysis_signal || "-"}
            tone={toneForSignal(row.original.analysis_signal)}
            dot={false}
          />
        ),
      },
      {
        accessorKey: "derived_intent",
        header: "Intent",
        cell: ({ row }) => (
          <StatusBadge
            label={row.original.derived_intent || "NONE"}
            tone={toneForOutcome(row.original.derived_intent)}
            dot={false}
          />
        ),
      },
      {
        accessorKey: "requested_execution_action",
        header: "Plan → Actual",
        cell: ({ row }) => {
          const requested = row.original.requested_execution_action || row.original.derived_intent || "NONE";
          const actual = row.original.actual_execution_action || (row.original.broker_order_submitted ? row.original.final_execution_action || "UNKNOWN" : "NOT_SUBMITTED");
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge label={`Plan: ${requested}`} tone={toneForOutcome(requested)} dot={false} />
              <StatusBadge
                label={`Actual: ${actual}`}
                tone={row.original.broker_order_submitted ? toneForOutcome(actual) : "neutral"}
                dot={false}
              />
            </div>
          );
        },
      },
      {
        accessorKey: "why_no_broker_order_code",
        header: "لماذا لا يوجد أمر وسيط؟",
        cell: ({ row }) => {
          const badge = whyNoBrokerBadge(row.original);
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge label={badge.label} tone={badge.tone} dot={false} />
              <span className="cell-muted" style={{ fontSize: 11 }}>
                {reasonCodeForRow(row.original)}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "execution_engine_status",
        header: "Execution State",
        cell: ({ row }) => (
          <div style={{ display: "grid", gap: 4 }}>
            <StatusBadge
              label={row.original.execution_engine_status || row.original.queue_status || "-"}
              tone={toneForExecutionEngineStatus(row.original.execution_engine_status || row.original.queue_status)}
              dot={false}
            />
            <StatusBadge
              label={row.original.execution_final_status || "-"}
              tone={toneForOutcome(row.original.execution_final_status)}
              dot={false}
            />
          </div>
        ),
      },
      {
        accessorKey: "broker_submission_status",
        header: "Broker Lifecycle",
        cell: ({ row }) => (
          <div style={{ display: "grid", gap: 4 }}>
            <StatusBadge
              label={row.original.broker_submission_status || "-"}
              tone={toneForBrokerSubmissionStatus(row.original.broker_submission_status)}
              dot={false}
            />
            <StatusBadge
              label={row.original.broker_lifecycle_status || "-"}
              tone={toneForOutcome(row.original.broker_lifecycle_status)}
              dot={false}
            />
          </div>
        ),
      },
      {
        accessorKey: "reconciliation_poll_count",
        header: "Reconciliation",
        cell: ({ row }) => {
          const pollCount = Number(row.original.reconciliation_poll_count || 0);
          const started = Boolean(row.original.reconciliation_started_at);
          const completed = Boolean(row.original.reconciliation_completed_at);
          const label = started
            ? completed
              ? "completed"
              : "running"
            : "not_started";
          const extra = row.original.reconciliation_window_expired
            ? "window_expired"
            : row.original.reconciliation_stop_reason || "-";
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge
                label={label}
                tone={toneForReconciliation(row.original)}
                dot={false}
              />
              <span className="cell-muted" style={{ fontSize: 11 }}>
                polls={pollCount} | {extra}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "retry_attempt_count",
        header: "Retry/Backoff",
        cell: ({ row }) => {
          const attempts = Number(row.original.retry_attempt_count || 0);
          const scheduled = row.original.retry_eligible && row.original.retry_next_attempt_at;
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge
                label={scheduled ? "retry_scheduled" : row.original.retry_exhausted ? "retry_exhausted" : "no_retry"}
                tone={scheduled ? "warning" : row.original.retry_exhausted ? "negative" : "neutral"}
                dot={false}
              />
              <span className="cell-muted" style={{ fontSize: 11 }}>
                attempts={attempts} backoff={Number(row.original.backoff_seconds || 0).toFixed(1)}s
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "guardrail_result",
        header: "Guardrail",
        cell: ({ row }) => (
          <StatusBadge
            label={row.original.guardrail_result || "-"}
            tone={toneForGuardrail(row.original.guardrail_result)}
            dot={false}
          />
        ),
      },
      {
        accessorKey: "broker_order_submitted",
        header: "Broker",
        cell: ({ row }) => (
          <StatusBadge
            label={row.original.broker_order_submitted ? "Submitted this cycle" : "No broker call this cycle"}
            tone={row.original.broker_order_submitted ? "positive" : "neutral"}
            dot={false}
          />
        ),
      },
      {
        accessorKey: "broker_order_status",
        header: "Broker Status",
        cell: ({ row }) => {
          const status = brokerStatusDisplay(row.original);
          return <StatusBadge label={status.label} tone={status.tone} dot={false} />;
        },
      },
      {
        accessorKey: "final_outcome_code",
        header: "Final Outcome",
        cell: ({ row }) => (
          <StatusBadge
            label={row.original.final_outcome_code || "-"}
            tone={toneForOutcome(row.original.final_outcome_code)}
            dot={false}
          />
        ),
      },
      {
        accessorKey: "current_position_pct",
        header: "Position → Target",
        cell: ({ row }) => {
          const currentPct = Number(row.original.current_position_pct || 0);
          const targetPct = Number(row.original.target_position_pct || 0);
          const addableValue = Number(row.original.addable_value || 0);
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <span className="cell-mono">
                {currentPct.toFixed(2)}% → {targetPct.toFixed(2)}%
              </span>
              <span className="cell-muted" style={{ fontSize: 11 }}>
                Addable ${addableValue.toFixed(2)}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "opportunity_score",
        header: "Opportunity",
        cell: ({ row }) => {
          const score = Number(row.original.opportunity_score || 0);
          const rank = row.original.portfolio_priority_rank || "-";
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <span className="cell-mono">{score.toFixed(2)}</span>
              <span className="cell-muted" style={{ fontSize: 11 }}>
                Rank #{rank}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "dl_signal",
        header: "ML / DL / Kronos",
        cell: ({ row }) => {
          const mlLabel = row.original.ml_ready
            ? `ML ${row.original.ml_signal || "-"} | ${Number(row.original.ml_contribution_to_score || 0).toFixed(4)}`
            : `ML ${row.original.ml_reason_not_used || "not_ready"}`;
          const dlLabel = row.original.dl_ready
            ? `DL ${row.original.dl_signal || "-"} | ${Number(row.original.dl_contribution_to_score || 0).toFixed(4)}`
            : `DL ${row.original.dl_reason_not_used || "not_ready"}`;
          const kronosLabel = row.original.kronos_ready
            ? `Kronos ${Number(row.original.kronos_score || 0).toFixed(1)} | ${Number(row.original.kronos_contribution_to_score || 0).toFixed(4)}`
            : `Kronos ${row.original.kronos_reason_not_used || row.original.kronos_wait_reason || "not_ready"}`;
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge label={mlLabel} tone={toneForComponentContribution(row.original.ml_contributed, row.original.ml_ready)} dot={false} />
              <StatusBadge label={dlLabel} tone={toneForComponentContribution(row.original.dl_contributed, row.original.dl_ready)} dot={false} />
              <StatusBadge label={kronosLabel} tone={toneForComponentContribution(row.original.kronos_contributed, row.original.kronos_ready)} dot={false} />
            </div>
          );
        },
      },
      {
        accessorKey: "kronos_score",
        header: "Kronos",
        cell: ({ row }) => {
          const score = Number(row.original.kronos_score || 0);
          const action = row.original.kronos_session_preferred_action || "-";
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge
                label={row.original.kronos_ready ? `score ${score.toFixed(1)}` : "not_ready"}
                tone={row.original.kronos_ready ? (score >= 65 ? "positive" : score >= 50 ? "warning" : "neutral") : "neutral"}
                dot={false}
              />
              <span className="cell-muted" style={{ fontSize: 11 }}>
                {action}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "funding_status",
        header: "Funding",
        cell: ({ row }) => {
          const status = row.original.funding_status || (row.original.funded ? "fully_funded" : "unfunded");
          const ratio = Number(row.original.funding_ratio || 0);
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge label={status} tone={toneForFundingStatus(status)} dot={false} />
              <span className="cell-muted" style={{ fontSize: 11 }}>
                Ratio {(ratio * 100).toFixed(0)}%
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "execution_priority_band",
        header: "Priority",
        cell: ({ row }) => {
          const band = row.original.execution_priority_band || "normal";
          return <StatusBadge label={band} tone={toneForPriorityBand(band)} dot={false} />;
        },
      },
      {
        accessorKey: "queue_rank",
        header: "Queue",
        cell: ({ row }) => {
          const rank = row.original.queue_rank;
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <span className="cell-mono">#{rank ?? "-"}</span>
              <span className="cell-muted" style={{ fontSize: 11 }}>
                {row.original.execution_stage || "-"}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "queue_status",
        header: "Queue Status",
        cell: ({ row }) => {
          const status = row.original.queue_status || "-";
          const dep = row.original.dependency_type || "none";
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge label={status} tone={toneForQueueStatus(status)} dot={false} />
              <span className="cell-muted" style={{ fontSize: 11 }}>
                dep: {dep}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "queue_gate_result",
        header: "Queue Gate",
        cell: ({ row }) => {
          const gate = row.original.queue_gate_result || "-";
          const reason = row.original.queue_gate_reason || row.original.defer_reason || "-";
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <StatusBadge label={gate} tone={toneForQueueGate(gate)} dot={false} />
              <span className="cell-muted" style={{ fontSize: 11 }}>{reason}</span>
            </div>
          );
        },
      },
      {
        accessorKey: "funding_decision",
        header: "Capital Decision",
        cell: ({ row }) => (
          <div style={{ display: "grid", gap: 4 }}>
            <StatusBadge
              label={row.original.funding_decision || (row.original.funded ? "funded" : "unfunded")}
              tone={toneForOutcome(row.original.funding_decision || row.original.capital_competition_reason)}
              dot={false}
            />
            <span className="cell-muted" style={{ fontSize: 11 }}>
              {row.original.partial_funding_reason || row.original.capital_competition_reason || "-"}
            </span>
          </div>
        ),
      },
      {
        accessorKey: "capital_requested_value",
        header: "Capital/Qty Req → Approved",
        cell: ({ row }) => {
          const requested = Number(row.original.capital_requested_value || 0);
          const approved = Number(row.original.capital_approved_value || 0);
          const requestedQty = Number(row.original.requested_order_qty || 0);
          const approvedQty = Number(row.original.approved_order_qty || 0);
          const recomputedQty = Number(row.original.recomputed_approved_order_qty || approvedQty || 0);
          const recomputedCapital = Number(row.original.recomputed_capital_approved_value || approved || 0);
          const resized = Boolean(row.original.resized_after_execution_result);
          return (
            <div style={{ display: "grid", gap: 4 }}>
              <span className="cell-mono">${requested.toFixed(2)} → ${approved.toFixed(2)}</span>
              <span className="cell-muted" style={{ fontSize: 11 }}>
                Qty {requestedQty.toFixed(4)} → {approvedQty.toFixed(4)}
              </span>
              {resized ? (
                <span className="cell-muted" style={{ fontSize: 11 }}>
                  Re-sized: ${recomputedCapital.toFixed(2)} | Qty {recomputedQty.toFixed(4)}
                </span>
              ) : null}
            </div>
          );
        },
      },
      {
        accessorKey: "confidence",
        header: "Confidence",
        cell: ({ row }) => (
          <span className="cell-mono">{Number(row.original.confidence || 0).toFixed(2)}</span>
        ),
      },
    ],
    []
  );

  const selectedReason = selectedRow ? reasonMetaForRow(selectedRow) : null;
  const selectedBadge = selectedRow ? whyNoBrokerBadge(selectedRow) : null;
  const selectedBrokerStatus = selectedRow ? brokerStatusDisplay(selectedRow) : { label: "-", tone: "neutral" };
  const selectedNoBrokerCall = selectedRow ? !selectedRow.broker_order_submitted : false;
  const selectedForecastChart = Array.isArray(selectedRow?.ai_engine_contribution_chart)
    ? selectedRow.ai_engine_contribution_chart
    : [];
  const selectedRewardComponents = Array.isArray(selectedRow?.reward_components) ? selectedRow.reward_components : [];
  const selectedPenaltyComponents = Array.isArray(selectedRow?.penalty_components) ? selectedRow.penalty_components : [];

  return (
    <PageFrame
      title="تشخيص قرارات التداول الآلي"
      description="سلسلة قرار كاملة لكل رمز: Signal → Intent → Guardrails → Broker → Final Outcome."
      eyebrow="Diagnostics"
      headerActions={
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-secondary btn-sm"
            type="button"
            onClick={() => loadCycles().catch(() => {})}
            disabled={cyclesLoading || cycleLoading}
          >
            تحديث
          </button>
          {cycle?.cycle_id ? (
            <a
              className="btn btn-secondary btn-sm"
              href={getAutoTradingDiagnosticsExportUrl(cycle.cycle_id)}
              target="_blank"
              rel="noreferrer"
            >
              CSV
            </a>
          ) : null}
        </div>
      }
    >
      <ErrorBanner message={cyclesError || cycleError} />

      <div className="info-banner" style={{ marginBottom: 12 }}>
        <b>قاعدة مهمة:</b> ظهور <b>Signal BUY</b> لا يعني تلقائيًا إرسال أمر شراء للوسيط. التنفيذ يعتمد على المركز الحالي، الحواجز، وحالة الوسيط/الجلسة.
      </div>

      <SectionCard title="اختيار الدورة" description="اختر دورة حديثة لعرض التشخيص. التحميل الأولي الآن بنمط Slim لتسريع الصفحة.">
        {cyclesLoading ? (
          <LoadingSkeleton lines={2} />
        ) : (
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "2fr 1fr 1fr 1fr" }}>
            <select
              className="input"
              value={selectedCycleId}
              onChange={(event) => setSelectedCycleId(event.target.value)}
            >
              {!cycles.length ? <option value="">لا توجد دورات</option> : null}
              {cycles.map((item) => (
                <option key={item.cycle_id} value={item.cycle_id}>
                  {item.cycle_id} | {item.cycle_started_at || "-"}
                </option>
              ))}
            </select>
            <div className="settings-row-value">Runtime: {cycle?.runtime_state || "-"}</div>
            <div className="settings-row-value">Delegated: {String(cycle?.delegated ?? "-")}</div>
            <div className="settings-row-value">Rows: {cycle?.rows_count ?? rows.length}</div>
          </div>
        )}
      </SectionCard>

      {cycleLoading ? (
        <LoadingSkeleton lines={6} />
      ) : !cycle ? (
        <SectionCard title="لا توجد بيانات" description="ستظهر بيانات التشخيص بعد اكتمال دورة auto-trading.">
          <div className="empty-state">
            <span className="empty-state-title">No diagnostics yet</span>
          </div>
        </SectionCard>
      ) : (
        <>
          <SectionCard title="ملخص الإشارات" description="هذه الأرقام تخص التحليل (Signals) وليست أوامر الوسيط.">
            <SummaryStrip items={signalSummaryItems} />
          </SectionCard>

          <SectionCard title="ملخص التنفيذ" description="هذه الأرقام تخص التنفيذ الفعلي وأوامر الوسيط.">
            <SummaryStrip items={executionSummaryItems} />
          </SectionCard>

          <SectionCard title="Market Session Status" description="مصدر الحقيقة لحالة السوق والجلسة الحالية.">
            <SummaryStrip items={sessionSummaryItems} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              <StatusBadge label={`Next Open: ${marketSession?.next_open_at || "-"}`} tone="neutral" dot={false} />
              <StatusBadge label={`Next Close: ${marketSession?.next_close_at || "-"}`} tone="neutral" dot={false} />
              <StatusBadge label={`Readiness Phase: ${marketSession?.readiness_phase || "-"}`} tone="info" dot={false} />
              <StatusBadge label={`Session Quality: ${marketSession?.session_quality || "-"}`} tone="warning" dot={false} />
            </div>
          </SectionCard>

          <SectionCard title="Market Readiness" description="تجهيز ما قبل الافتتاح وتخطيط تنفيذ الجلسة.">
            <SummaryStrip items={readinessSummaryItems} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              <StatusBadge label={`Pre-market budget: ${Number(marketReadiness?.premarket_capital_budget || 0).toFixed(2)}`} tone="info" dot={false} />
              <StatusBadge label={`Queued budget: ${Number(marketReadiness?.queued_for_open_budget || 0).toFixed(2)}`} tone="warning" dot={false} />
              <StatusBadge label={`Reserved for open: ${Number(marketReadiness?.capital_reserved_for_open || 0).toFixed(2)}`} tone="warning" dot={false} />
              <StatusBadge label={`Wait-for-open: ${Number(marketReadiness?.wait_for_open_confirmation_count || 0)}`} tone="neutral" dot={false} />
              <StatusBadge label={`Pre-market exposure used: ${Number(marketReadiness?.premarket_exposure_used || 0).toFixed(2)}`} tone="neutral" dot={false} />
              <StatusBadge label={`Pre-market exposure remaining: ${Number(marketReadiness?.premarket_exposure_remaining || 0).toFixed(2)}`} tone="neutral" dot={false} />
            </div>
            {Array.isArray(marketReadiness?.readiness_warnings) && marketReadiness.readiness_warnings.length ? (
              <div className="cell-muted" style={{ marginTop: 8, fontSize: 12 }}>
                {marketReadiness.readiness_warnings.join(" | ")}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Desk Brief" description="الملخص التشغيلي للجلسة: أفضل الفرص، رأس المال المحجوز للافتتاح، وأهم أسباب التأجيل أو الحظر.">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
              <StatusBadge label={`Desk session: ${deskBrief?.session_state || "-"}`} tone="info" dot={false} />
              <StatusBadge label={`Desk phase: ${deskBrief?.readiness_phase || "-"}`} tone="neutral" dot={false} />
              <StatusBadge label={`Reserved capital: ${Number(deskBrief?.reserved_capital || 0).toFixed(2)}`} tone="warning" dot={false} />
              <StatusBadge label={`Reserve reason: ${deskBrief?.reserved_capital_reason || "-"}`} tone="warning" dot={false} />
            </div>
            {deskBriefRiskFlags.length ? (
              <div style={{ display: "grid", gap: 6, marginBottom: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Session risk flags:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {deskBriefRiskFlags.slice(0, 8).map(([flag, count]) => (
                    <StatusBadge key={`${flag}-${count}`} label={`${flag}: ${count}`} tone="warning" dot={false} />
                  ))}
                </div>
              </div>
            ) : null}
            {Array.isArray(deskBrief?.top_ranked_ideas) && deskBrief.top_ranked_ideas.length ? (
              <div style={{ display: "grid", gap: 6 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Top ranked ideas:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {deskBrief.top_ranked_ideas.slice(0, 8).map((item) => (
                    <StatusBadge
                      key={`desk-top-${item.symbol}`}
                      label={`${item.symbol} | ${Number(item.score || 0).toFixed(1)} | ${item.action || item.plan || "-"}`}
                      tone={Number(item.score || 0) >= 70 ? "positive" : Number(item.score || 0) >= 55 ? "warning" : "neutral"}
                      dot={false}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Pre-Open Action Plan" description="من يمكن تداوله الآن، من يُصفّ للافتتاح، ومن ينتظر تأكيد الافتتاح.">
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ display: "grid", gap: 6 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Pre-market candidates</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {premarketCandidates.length ? premarketCandidates.slice(0, 8).map((item) => (
                    <StatusBadge
                      key={`premarket-${item.symbol}`}
                      label={`${item.symbol} | ${Number(item.premarket_score || item.session_adjusted_opportunity_score || 0).toFixed(1)} | ${item.premarket_submit_reason || item.session_preferred_action || "-"}`}
                      tone="positive"
                      dot={false}
                    />
                  )) : <StatusBadge label="No pre-market live candidates" tone="neutral" dot={false} />}
                </div>
              </div>
              <div style={{ display: "grid", gap: 6 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Queued for open</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {queuedForOpenCandidates.length ? queuedForOpenCandidates.slice(0, 8).map((item) => (
                    <StatusBadge
                      key={`queue-open-${item.symbol}`}
                      label={`${item.symbol} | rank ${item.portfolio_priority_rank || "-"} | ${item.queued_for_open_reason || item.session_preferred_action || "-"}`}
                      tone="warning"
                      dot={false}
                    />
                  )) : <StatusBadge label="No queued-for-open candidates" tone="neutral" dot={false} />}
                </div>
              </div>
              <div style={{ display: "grid", gap: 6 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Waiting for open confirmation</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {waitForOpenCandidates.length ? waitForOpenCandidates.slice(0, 8).map((item) => (
                    <StatusBadge
                      key={`wait-open-${item.symbol}`}
                      label={`${item.symbol} | ${Number(item.open_confirmation_score || item.session_adjusted_opportunity_score || 0).toFixed(1)} | ${item.wait_for_open_reason || "-"}`}
                      tone="neutral"
                      dot={false}
                    />
                  )) : <StatusBadge label="No wait-for-open-confirmation candidates" tone="neutral" dot={false} />}
                </div>
              </div>
              <div style={{ display: "grid", gap: 6 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Reductions / exits before open</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {preopenReduceCandidates.length ? preopenReduceCandidates.slice(0, 8).map((item) => (
                    <StatusBadge
                      key={`reduce-open-${item.symbol}`}
                      label={`${item.symbol} | ${item.requested_execution_action || item.session_preferred_action || "-"} | ${item.session_order_plan || "-"}`}
                      tone={item.requested_execution_action === "EXIT_LONG" ? "negative" : "warning"}
                      dot={false}
                    />
                  )) : <StatusBadge label="No reduction/exit-before-open candidates" tone="neutral" dot={false} />}
                </div>
              </div>
              {marketReadiness?.no_trade_reasons && Object.keys(marketReadiness.no_trade_reasons).length ? (
                <div style={{ display: "grid", gap: 6 }}>
                  <div className="cell-muted" style={{ fontSize: 12 }}>No-trade / defer reasons</div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {Object.entries(marketReadiness.no_trade_reasons).slice(0, 8).map(([reason, count]) => (
                      <StatusBadge key={`${reason}-${count}`} label={`${reason}: ${count}`} tone="warning" dot={false} />
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </SectionCard>

          <SectionCard title="Kronos Intelligence Layer" description="Kronos يضيف ذكاء OHLCV للجلسة، التوقيت، والحجم دون استبدال المنظومة الأساسية.">
            <SummaryStrip items={kronosSummaryItems} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              <StatusBadge label={`Model: ${kronosStatus?.kronos_model_name || "-"}`} tone="neutral" dot={false} />
              <StatusBadge label={`Device: ${kronosStatus?.kronos_device || "-"}`} tone="neutral" dot={false} />
              <StatusBadge label={`Ready: ${kronosStatus?.kronos_ready ? "YES" : "NO"}`} tone={kronosStatus?.kronos_ready ? "positive" : "warning"} dot={false} />
              <StatusBadge label={`Last inference: ${kronosStatus?.kronos_last_inference_at || "-"}`} tone="neutral" dot={false} />
            </div>
            {kronosTopSymbols.length ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Kronos top signals:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {kronosTopSymbols.map((row) => (
                    <StatusBadge
                      key={`kronos-${row.symbol}`}
                      label={`${row.symbol} | score ${Number(row.kronos_score || 0).toFixed(1)} | ${row.kronos_session_preferred_action || row.session_order_plan || "-"}`}
                      tone={Number(row.kronos_score || 0) >= 65 ? "positive" : Number(row.kronos_score || 0) >= 50 ? "warning" : "neutral"}
                      dot={false}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Analysis Engine Status" description="فصل صريح بين classic / ranking / ML / DL / Kronos مع حقيقة الاستخدام في آخر دورة غير فارغة.">
            <SummaryStrip items={analysisEngineSummaryItems} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              <StatusBadge label={`Strategy Mode: ${analysisEnginesStatus?.strategy_mode || "-"}`} tone="info" dot={false} />
              <StatusBadge label={`ML reason: ${analysisEnginesStatus?.ml?.status_reason || "-"}`} tone={analysisEnginesStatus?.ml?.ready ? "positive" : "warning"} dot={false} />
              <StatusBadge label={`DL reason: ${analysisEnginesStatus?.dl?.status_reason || "-"}`} tone={analysisEnginesStatus?.dl?.ready ? "positive" : "warning"} dot={false} />
              <StatusBadge label={`DL resolution: ${analysisEnginesStatus?.dl?.resolution || "-"}`} tone={analysisEnginesStatus?.dl?.fallback_used ? "warning" : "positive"} dot={false} />
              <StatusBadge label={`Kronos source: ${analysisEnginesStatus?.kronos?.status_source || kronosStatus?.kronos_status_source || "-"}`} tone="neutral" dot={false} />
              <StatusBadge label={`Kronos batch cache: ${kronosStatus?.kronos_batch_cache_ready ? "READY" : "NO"}`} tone={kronosStatus?.kronos_batch_cache_ready ? "positive" : "warning"} dot={false} />
              <StatusBadge label={`Kronos cache age s: ${Number(kronosStatus?.kronos_cache_age_seconds || kronosStatus?.kronos_batch_cache?.kronos_cache_age_seconds || 0).toFixed(1)}`} tone="neutral" dot={false} />
            </div>
            {analysisEnginesStatus?.latest_cycle?.example_engine_contribution ? (
              <div className="cell-muted" style={{ marginTop: 8, fontSize: 12 }}>
                Example live contribution: {analysisEnginesStatus.latest_cycle.example_engine_contribution.symbol} | DL {String(analysisEnginesStatus.latest_cycle.example_engine_contribution.dl_signal || "-")} ({Number(analysisEnginesStatus.latest_cycle.example_engine_contribution.dl_contribution_to_score || 0).toFixed(4)}) | Kronos {Number(analysisEnginesStatus.latest_cycle.example_engine_contribution.kronos_contribution_to_score || 0).toFixed(4)}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Market Regime Brain" description="النظام يغيّر شهية المخاطر قبل اختيار الرموز.">
            <SummaryStrip items={regimeSummaryItems} />
            {Array.isArray(regime?.notes) && regime.notes.length ? (
              <div className="cell-muted" style={{ marginTop: 8, fontSize: 12 }}>
                {regime.notes.join(" | ")}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Portfolio Allocation Brain" description="تخصيص رأس المال يتم بالمنافسة بين الفرص وليس بالموافقة المستقلة لكل BUY.">
            <SummaryStrip items={portfolioActionItems} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              <StatusBadge label={`Symbols considered: ${allocationSummary?.symbols_considered ?? allocationLedger?.candidates_total ?? 0}`} tone="info" dot={false} />
              <StatusBadge label={`Funded: ${allocationSummary?.funded_count ?? allocationLedger?.funded_total ?? 0}`} tone="positive" dot={false} />
              <StatusBadge label={`Full funded: ${allocationSummary?.funded_full_count ?? allocationLedger?.funded_full_count ?? 0}`} tone="positive" dot={false} />
              <StatusBadge label={`Partial funded: ${allocationSummary?.funded_partial_count ?? allocationLedger?.funded_partial_count ?? 0}`} tone="warning" dot={false} />
              <StatusBadge label={`Unfunded: ${allocationLedger?.unfunded_count ?? allocationLedger?.unfunded_total ?? 0}`} tone="warning" dot={false} />
              <StatusBadge label={`Reduced: ${allocationLedger?.reduced_total ?? 0}`} tone="warning" dot={false} />
              <StatusBadge label={`Exited: ${allocationLedger?.exited_total ?? 0}`} tone="negative" dot={false} />
              <StatusBadge label={`Partial capital: ${Number(allocationLedger?.partial_capital_total || 0).toFixed(2)}`} tone="info" dot={false} />
              <StatusBadge label={`Capital reserved: ${Number(allocationLedger?.capital_reserved_value || 0).toFixed(2)}`} tone="neutral" dot={false} />
              <StatusBadge label={`Capital left: ${Number(allocationLedger?.capital_left_unallocated || 0).toFixed(2)}`} tone="neutral" dot={false} />
              <StatusBadge label={`Cash used: ${Number(allocationSummary?.capital?.cash_used_for_allocations || 0).toFixed(2)}`} tone="warning" dot={false} />
              <StatusBadge label={`Cash remaining: ${Number(allocationSummary?.capital?.cash_remaining || allocationLedger?.available_cash_after || 0).toFixed(2)}`} tone="neutral" dot={false} />
              <StatusBadge label={`Regime budget: ${Number(allocationSummary?.capital?.regime_adjusted_budget || allocationLedger?.regime_adjusted_budget || 0).toFixed(2)}`} tone="info" dot={false} />
              <StatusBadge label={`Slots: ${allocationLedger?.portfolio_slot_consumed ?? 0}/${allocationLedger?.max_new_positions ?? 0}`} tone="neutral" dot={false} />
            </div>
            {highestUnfunded.length ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Strong ideas not funded this cycle:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {highestUnfunded.slice(0, 5).map((item) => (
                    <StatusBadge
                      key={`${item.symbol}-${item.reason}`}
                      label={`${item.symbol} | ${Number(item.opportunity_score || 0).toFixed(1)} | ${item.reason || "-"}`}
                      tone="neutral"
                      dot={false}
                    />
                  ))}
                </div>
              </div>
            ) : null}
            {Array.isArray(selfReview?.top_blockers) && selfReview.top_blockers.length ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Top blockers:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {selfReview.top_blockers.slice(0, 5).map((item) => (
                    <StatusBadge
                      key={`${item.reason_code}-${item.count}`}
                      label={`${item.reason_code}: ${item.count}`}
                      tone="warning"
                      dot={false}
                    />
                  ))}
                </div>
              </div>
            ) : null}
            {allocationSummary?.top_capital_competition_reasons ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Capital competition reasons:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {Object.entries(allocationSummary.top_capital_competition_reasons).slice(0, 8).map(([key, count]) => (
                    <StatusBadge key={`${key}-${count}`} label={`${key}: ${count}`} tone="info" dot={false} />
                  ))}
                </div>
              </div>
            ) : null}
            {allocationLedger?.execution_priority_band_counts ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Execution priority bands:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {Object.entries(allocationLedger.execution_priority_band_counts).map(([band, count]) => (
                    <StatusBadge key={`${band}-${count}`} label={`${band}: ${count}`} tone={toneForPriorityBand(band)} dot={false} />
                  ))}
                </div>
              </div>
            ) : null}
            {Array.isArray(allocationSummary?.positions_marked_for_reduce_exit) && allocationSummary.positions_marked_for_reduce_exit.length ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Positions marked for Reduce/Exit:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {allocationSummary.positions_marked_for_reduce_exit.slice(0, 6).map((item) => (
                    <StatusBadge key={`${item.symbol}-${item.action}`} label={`${item.symbol} | ${item.action} | ${item.reason}`} tone="warning" dot={false} />
                  ))}
                </div>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Autonomous Trader Judgment" description="طبقة الحكم العليا التي تجمع الجلسة، النظام، جودة السوق، وتفضيل الاحتفاظ بالكاش قبل أي قرار شراء/إضافة/خفض/خروج.">
            <SummaryStrip items={marketJudgmentItems} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              {(marketJudgment?.market_warning_flags || []).slice(0, 8).map((flag) => (
                <StatusBadge key={flag} label={flag} tone="warning" dot={false} />
              ))}
              {(marketJudgment?.session_notes || []).slice(0, 4).map((note, idx) => (
                <StatusBadge key={`${note}-${idx}`} label={note} tone="neutral" dot={false} />
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Portfolio Sleeves" description="المحفظة تُدار كسلال ديناميكية: growth / quality / defense / tactical small caps / cash بدل وزن ثابت واحد.">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
              <StatusBadge label={`Size tier: ${portfolioSleeves?.portfolio_size_tier || "-"}`} tone="info" dot={false} />
              <StatusBadge label={`Cash target: ${Number(portfolioSleeves?.cash_target_pct || 0).toFixed(1)}%`} tone="neutral" dot={false} />
              <StatusBadge label={`Rotation pressure: ${Number(portfolioSleeves?.rotation_pressure_score || 0).toFixed(1)}`} tone={Number(portfolioSleeves?.rotation_pressure_score || 0) >= 65 ? "warning" : "neutral"} dot={false} />
              <StatusBadge label={`Sleeve shift: ${portfolioSleeves?.sleeve_shift_reason || "-"}`} tone="neutral" dot={false} />
            </div>
            <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
              {sleeveRows.map((item) => (
                <div key={item.sleeve} className="settings-row-value" style={{ display: "grid", gap: 4 }}>
                  <span className="cell-muted">{item.sleeve}</span>
                  <StatusBadge label={`Target ${item.target}%`} tone="info" dot={false} />
                  <StatusBadge label={`Actual ${item.actual}%`} tone="neutral" dot={false} />
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <StatusBadge label={`Max concentration ${Number(selfGovernedLimits?.max_effective_concentration_pct || 0).toFixed(1)}%`} tone="warning" dot={false} />
              <StatusBadge label={`Max small-cap exposure ${Number(selfGovernedLimits?.max_small_cap_exposure_pct || 0).toFixed(1)}%`} tone={Number(selfGovernedLimits?.max_small_cap_exposure_pct || 0) > 0 ? "info" : "neutral"} dot={false} />
              <StatusBadge label={`Max pre-market exposure ${Number(selfGovernedLimits?.max_premarket_exposure_pct || 0).toFixed(1)}%`} tone="info" dot={false} />
              <StatusBadge label={`Dynamic max new positions ${selfGovernedLimits?.max_open_new_positions_dynamic ?? 0}`} tone="neutral" dot={false} />
            </div>
          </SectionCard>

          <SectionCard title="Rotation & Tactical Ideas" description="من الأفضل الاحتفاظ به، من يمكن تدوير رأس المال منه، وأين توجد فرص small-cap التكتيكية عندما تسمح جودة السوق بذلك.">
            <div style={{ display: "grid", gap: 10 }}>
              <div>
                <div className="cell-muted" style={{ fontSize: 12, marginBottom: 6 }}>Rotation opportunities</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {rotationOpportunities.length ? rotationOpportunities.slice(0, 6).map((item, idx) => (
                    <StatusBadge
                      key={`${item.rotation_from_symbol}-${item.rotation_to_symbol}-${idx}`}
                      label={`${item.rotation_from_symbol || "-"} → ${item.rotation_to_symbol || "-"} | ${item.reason || "-"}`}
                      tone="warning"
                      dot={false}
                    />
                  )) : <StatusBadge label="No live rotation opportunity in this window" tone="neutral" dot={false} />}
                </div>
              </div>
              <div>
                <div className="cell-muted" style={{ fontSize: 12, marginBottom: 6 }}>Why not buying</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {whyNotBuying.length ? whyNotBuying.slice(0, 6).map((item, idx) => (
                    <StatusBadge
                      key={`${item.symbol}-${idx}`}
                      label={`${item.symbol} | ${item.reason || "-"} | ${item.detail || "-"}`}
                      tone="neutral"
                      dot={false}
                    />
                  )) : <StatusBadge label="No deferred buy explanation captured" tone="neutral" dot={false} />}
                </div>
              </div>
              <div>
                <div className="cell-muted" style={{ fontSize: 12, marginBottom: 6 }}>Small-cap tactical candidates</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {smallCapCandidates.length ? smallCapCandidates.slice(0, 6).map((item, idx) => (
                    <StatusBadge
                      key={`${item.symbol}-${idx}`}
                      label={`${item.symbol} | score ${Number(item.tactical_small_cap_score || 0).toFixed(1)} | ${item.action || "-"} | ${item.reason || "-"}`}
                      tone="info"
                      dot={false}
                    />
                  )) : <StatusBadge label="No tactical small-cap candidate in this cycle" tone="neutral" dot={false} />}
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Trade Review & Learning" description="مراجعة يومية/أسبوعية خفيفة تعاقب القرارات الرديئة وتكافئ جودة التخصيص والتوقيت، لا الربح الخام فقط.">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
              <StatusBadge label={`Trade reviews available: ${Number(selfReview?.historical_trade_reviews_available || 0)}`} tone="info" dot={false} />
              <StatusBadge label={`Pending reviews: ${Number(selfReview?.trade_review_pending_count || 0)}`} tone={Number(selfReview?.trade_review_pending_count || 0) > 0 ? "warning" : "neutral"} dot={false} />
              <StatusBadge label={`Daily posture quality: ${Number(dailyReview?.overall_market_posture_quality || 0).toFixed(1)}`} tone={Number(dailyReview?.overall_market_posture_quality || 0) >= 65 ? "positive" : "warning"} dot={false} />
              <StatusBadge label={`Cash usage quality: ${Number(dailyReview?.cash_usage_quality || 0).toFixed(1)}`} tone="neutral" dot={false} />
              <StatusBadge label={`Rotation quality: ${Number(dailyReview?.rotation_quality || 0).toFixed(1)}`} tone="warning" dot={false} />
              <StatusBadge label={`Weekly aggressiveness: ${Number(weeklyReview?.aggressiveness_score || 0).toFixed(1)}`} tone="info" dot={false} />
              <StatusBadge label={`Weekly wait discipline: ${Number(weeklyReview?.wait_discipline_score || 0).toFixed(1)}`} tone="neutral" dot={false} />
              <StatusBadge label={`Sleeve rebalance: ${weeklyReview?.sleeve_balance_hint || "-"}`} tone="warning" dot={false} />
            </div>
            <div style={{ display: "grid", gap: 8 }}>
              <div className="cell-muted" style={{ fontSize: 12 }}>
                Daily review: entries {Number(dailyReview?.entry_quality || 0).toFixed(1)} | adds {Number(dailyReview?.add_quality || 0).toFixed(1)} | exits {Number(dailyReview?.exit_quality || 0).toFixed(1)} | small caps {Number(dailyReview?.small_cap_participation_quality || 0).toFixed(1)} | news handling {Number(dailyReview?.news_handling_quality || 0).toFixed(1)}
              </div>
              <div className="cell-muted" style={{ fontSize: 12 }}>
                Weekly review: best styles {(weeklyReview?.best_trade_types || []).join(", ") || "-"} | failed styles {(weeklyReview?.weak_trade_types || []).join(", ") || "-"} | engine recalibration {weeklyReview?.engine_recalibration_hint || "-"}
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Execution Orchestrator Queue" description="بعد التمويل، الأوردرات تمر بطابور تنفيذ فعلي: ترتيب، تبعيات تحرير رأس المال، وحواجز الجلسة/الانزلاق.">
            <SummaryStrip items={queueSummaryItems} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              <StatusBadge label={`Max submissions: ${executionQueueSummary.max_submissions_per_cycle ?? "-"}`} tone="info" dot={false} />
              <StatusBadge label={`Spacing sec: ${executionQueueSummary.submission_spacing_seconds ?? "-"}`} tone="neutral" dot={false} />
              <StatusBadge label={`Symbol cooldown sec: ${executionQueueSummary.symbol_cooldown_seconds ?? "-"}`} tone="neutral" dot={false} />
              <StatusBadge label={`Recon started: ${executionQueueSummary.reconciliation_started_count ?? 0}`} tone="info" dot={false} />
              <StatusBadge label={`Recon terminal: ${executionQueueSummary.reconciliation_terminal_count ?? 0}`} tone="positive" dot={false} />
              <StatusBadge label={`Recon window expired: ${executionQueueSummary.reconciliation_window_expired_count ?? 0}`} tone={(executionQueueSummary.reconciliation_window_expired_count ?? 0) > 0 ? "warning" : "neutral"} dot={false} />
            </div>
            {executionQueueSummary?.execution_final_status_counts ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Execution final state counts:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {Object.entries(executionQueueSummary.execution_final_status_counts).map(([key, count]) => (
                    <StatusBadge key={`efs-${key}-${count}`} label={`${key}: ${count}`} tone={toneForOutcome(key)} dot={false} />
                  ))}
                </div>
              </div>
            ) : null}
            {submittedQueue.length ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Executed first (submission order):</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {submittedQueue.slice(0, 8).map((item, idx) => (
                    <StatusBadge
                      key={`sub-${item.queue_item_id || item.symbol || idx}`}
                      label={`#${item.submission_order || idx + 1} ${item.symbol} ${item.action || ""} (${item.execution_priority_band || "-"})`}
                      tone="positive"
                      dot={false}
                    />
                  ))}
                </div>
              </div>
            ) : null}
            {waitingQueue.length ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Waiting for capital release:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {waitingQueue.slice(0, 8).map((item) => (
                    <StatusBadge
                      key={`wait-${item.queue_item_id || item.symbol}`}
                      label={`${item.symbol} | ${item.requested_execution_action || "-"} | ${item.queue_gate_reason || item.dependency_outcome || "waiting"}`}
                      tone="warning"
                      dot={false}
                    />
                  ))}
                </div>
              </div>
            ) : null}
            {deferredQueue.length ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Deferred this cycle:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {deferredQueue.slice(0, 8).map((item, idx) => (
                    <StatusBadge
                      key={`def-${item.queue_item_id || item.symbol || idx}`}
                      label={`${item.symbol} | ${item.action || item.requested_execution_action || "-"} | ${item.reason || item.queue_gate_reason || "deferred"}`}
                      tone="warning"
                      dot={false}
                    />
                  ))}
                </div>
              </div>
            ) : null}
            {skippedQueue.length ? (
              <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <div className="cell-muted" style={{ fontSize: 12 }}>Skipped this cycle:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {skippedQueue.slice(0, 8).map((item, idx) => (
                    <StatusBadge
                      key={`skip-${item.queue_item_id || item.symbol || idx}`}
                      label={`${item.symbol} | ${item.action || item.requested_execution_action || "-"} | ${item.reason || item.queue_gate_reason || "skipped"}`}
                      tone="neutral"
                      dot={false}
                    />
                  ))}
                </div>
              </div>
            ) : null}
            {executionTimeline.length ? (
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: "pointer", fontWeight: 600 }}>Execution timeline (latest events)</summary>
                <pre className="code-block" style={{ marginTop: 8, maxHeight: 240, overflow: "auto" }}>
                  {JSON.stringify(executionTimeline.slice(-30), null, 2)}
                </pre>
              </details>
            ) : null}
          </SectionCard>

          <SectionCard title="مجموعات أسباب عدم الإرسال" description="تجميع سريع للأسباب الأعلى تأثيرًا.">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {Object.keys(reasonGroupCounts)
                .sort((a, b) => (reasonGroupCounts[b] || 0) - (reasonGroupCounts[a] || 0))
                .map((group) => {
                  const meta = groupMeta(group);
                  return (
                    <StatusBadge
                      key={group}
                      label={`${meta.label}: ${reasonGroupCounts[group] || 0}`}
                      tone={meta.tone}
                      dot={false}
                    />
                  );
                })}
            </div>
          </SectionCard>

          <SectionCard title="الفلاتر" description="اعزل الحالات بسرعة حسب السبب أو حالة التنفيذ.">
            <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(4, minmax(180px, 1fr))", alignItems: "center" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={blockedOnly} onChange={(event) => setBlockedOnly(event.target.checked)} />
                فقط المحجوب
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={submittedOnly} onChange={(event) => setSubmittedOnly(event.target.checked)} />
                فقط المرسل للوسيط
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={existingPositionOnly} onChange={(event) => setExistingPositionOnly(event.target.checked)} />
                فقط مركز قائم
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={marketClosedOnly} onChange={(event) => setMarketClosedOnly(event.target.checked)} />
                فقط السوق مغلق
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={riskBlockedOnly} onChange={(event) => setRiskBlockedOnly(event.target.checked)} />
                فقط محجوب مخاطر
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={brokerRejectedOnly} onChange={(event) => setBrokerRejectedOnly(event.target.checked)} />
                فقط رفض الوسيط
              </label>
              <select className="input" value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}>
                <option value="">كل رموز الأسباب</option>
                {reasonCodes.map((code) => (
                  <option key={code} value={code}>{code}</option>
                ))}
              </select>
              <select className="input" value={actionType} onChange={(event) => setActionType(event.target.value)}>
                <option value="">كل أنواع الحركة</option>
                {actionTypes.map((code) => (
                  <option key={code} value={code}>{code}</option>
                ))}
              </select>
              <select className="input" value={fundingStatus} onChange={(event) => setFundingStatus(event.target.value)}>
                <option value="">كل حالات التمويل</option>
                <option value="full">تمويل كامل</option>
                <option value="partial">تمويل جزئي</option>
                <option value="unfunded">غير ممول</option>
              </select>
              <select className="input" value={priorityBand} onChange={(event) => setPriorityBand(event.target.value)}>
                <option value="">كل الأولويات</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="normal">Normal</option>
                <option value="low">Low</option>
                <option value="deferred">Deferred</option>
              </select>
              <select className="input" value={queueStatus} onChange={(event) => setQueueStatus(event.target.value)}>
                <option value="">كل حالات الطابور</option>
                <option value="submitted">submitted</option>
                <option value="waiting_for_prerequisite">waiting_for_prerequisite</option>
                <option value="deferred">deferred</option>
                <option value="skipped">skipped</option>
              </select>
            </div>
          </SectionCard>

          <SectionCard
            title="Decision Chain Table"
            description="Signal لا يساوي تنفيذ. راقب عمود: لماذا لا يوجد أمر وسيط؟"
            action={<StatusBadge label={`${filteredRows.length} / ${rows.length}`} tone="info" dot={false} />}
          >
            <DataTable
              columns={columns}
              data={filteredRows}
              emptyTitle="لا توجد صفوف مطابقة"
              emptyDescription="غيّر الفلاتر أو اختر دورة أخرى."
              maxHeight={520}
            />
          </SectionCard>

          <SectionCard
            title={selectedRow ? `تفاصيل ${selectedRow.symbol}` : "تفاصيل الرمز"}
            description="التفاصيل الثقيلة تُحمّل عند فتح الرمز فقط."
          >
            {!selectedRow ? (
              <div className="empty-state">
                <span className="empty-state-title">اختر رمزًا من الجدول لعرض التفاصيل</span>
              </div>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                <div className="command-grid" style={{ gridTemplateColumns: "repeat(4, minmax(170px, 1fr))" }}>
                  <Metric label="Signal" value={selectedRow.analysis_signal} tone={toneForSignal(selectedRow.analysis_signal)} />
                  <Metric label="Intent" value={selectedRow.derived_intent} tone={toneForOutcome(selectedRow.derived_intent)} />
                  <Metric
                    label="Requested Action"
                    value={selectedRow.requested_execution_action || "NONE"}
                    tone={toneForOutcome(selectedRow.requested_execution_action || selectedRow.derived_intent)}
                  />
                  <Metric
                    label="Actual Action"
                    value={selectedRow.actual_execution_action || (selectedNoBrokerCall ? "NOT_SUBMITTED" : "-")}
                    tone={selectedNoBrokerCall ? "neutral" : toneForOutcome(selectedRow.actual_execution_action)}
                  />
                  <Metric
                    label="Execution Engine Status"
                    value={selectedRow.execution_engine_status || "-"}
                    tone={toneForExecutionEngineStatus(selectedRow.execution_engine_status)}
                  />
                  <Metric
                    label="Broker Submission Status"
                    value={selectedRow.broker_submission_status || "-"}
                    tone={toneForBrokerSubmissionStatus(selectedRow.broker_submission_status)}
                  />
                  <Metric
                    label="Broker Lifecycle Status"
                    value={selectedRow.broker_lifecycle_status || "-"}
                    tone={toneForOutcome(selectedRow.broker_lifecycle_status)}
                  />
                  <Metric
                    label="Execution Final Status"
                    value={selectedRow.execution_final_status || "-"}
                    tone={toneForOutcome(selectedRow.execution_final_status)}
                  />
                  <Metric label="Guardrail" value={selectedRow.guardrail_result} tone={toneForGuardrail(selectedRow.guardrail_result)} />
                  <Metric label="Final Outcome" value={selectedRow.final_outcome_code} tone={toneForOutcome(selectedRow.final_outcome_code)} />
                  <Metric
                    label="Decision Outcome"
                    value={selectedRow.decision_outcome_code || selectedRow.final_outcome_code || "-"}
                    tone={toneForOutcome(selectedRow.decision_outcome_code || selectedRow.final_outcome_code)}
                  />
                  <Metric
                    label="Execution Outcome"
                    value={selectedRow.execution_outcome_code || selectedRow.broker_outcome_code || "-"}
                    tone={toneForOutcome(selectedRow.execution_outcome_code || selectedRow.broker_outcome_code)}
                  />
                  <Metric
                    label="Execution Skip Reason"
                    value={selectedRow.execution_skip_reason || "-"}
                    tone={selectedRow.execution_skip_reason ? "warning" : "neutral"}
                  />
                  <Metric label="Queue Rank" value={selectedRow.queue_rank ?? "-"} tone="info" />
                  <Metric label="Queue Status" value={selectedRow.queue_status || "-"} tone={toneForQueueStatus(selectedRow.queue_status)} />
                  <Metric label="Queue Gate" value={selectedRow.queue_gate_result || "-"} tone={toneForQueueGate(selectedRow.queue_gate_result)} />
                  <Metric label="Engine Submitted At" value={selectedRow.submitted_to_execution_engine_at || "-"} tone="neutral" />
                  <Metric label="Broker Attempted At" value={selectedRow.broker_submission_attempted_at || "-"} tone="neutral" />
                  <Metric label="Broker Ack At" value={selectedRow.broker_acknowledged_at || "-"} tone="neutral" />
                  <Metric label="Broker Last Update" value={selectedRow.broker_last_update_at || "-"} tone="neutral" />
                  <Metric label="Execution Completed At" value={selectedRow.execution_completed_at || "-"} tone="neutral" />
                  <Metric label="First Fill At" value={selectedRow.first_fill_at || "-"} tone="neutral" />
                  <Metric label="Final Fill At" value={selectedRow.final_fill_at || "-"} tone="neutral" />
                  <Metric label="Recon Started At" value={selectedRow.reconciliation_started_at || "-"} tone={selectedRow.reconciliation_started_at ? "info" : "neutral"} />
                  <Metric label="Recon Last Poll" value={selectedRow.reconciliation_last_polled_at || "-"} tone={selectedRow.reconciliation_last_polled_at ? "info" : "neutral"} />
                  <Metric label="Recon Completed At" value={selectedRow.reconciliation_completed_at || "-"} tone={selectedRow.reconciliation_completed_at ? "positive" : "neutral"} />
                  <Metric label="Recon Poll Count" value={selectedRow.reconciliation_poll_count ?? 0} tone="neutral" />
                  <Metric label="Recon Terminal" value={selectedRow.reconciliation_terminal ? "Yes" : "No"} tone={selectedRow.reconciliation_terminal ? "positive" : "neutral"} />
                  <Metric label="Recon Window Expired" value={selectedRow.reconciliation_window_expired ? "Yes" : "No"} tone={selectedRow.reconciliation_window_expired ? "warning" : "neutral"} />
                  <Metric label="Recon Stop Reason" value={selectedRow.reconciliation_stop_reason || "-"} tone={selectedRow.reconciliation_stop_reason ? "warning" : "neutral"} />
                  <Metric label="Queue Reason" value={selectedRow.queue_reason || selectedRow.queue_gate_reason || selectedRow.defer_reason || "-"} tone="neutral" />
                  <Metric label="Dependency" value={selectedRow.dependency_type || "none"} tone={selectedRow.dependency_type && selectedRow.dependency_type !== "none" ? "warning" : "neutral"} />
                  <Metric label="Dependency Outcome" value={selectedRow.dependency_final_outcome || selectedRow.dependency_outcome || "-"} tone={toneForOutcome(selectedRow.dependency_final_outcome || selectedRow.dependency_outcome)} />
                  <Metric label="Expected Release $" value={Number(selectedRow.dependency_expected_release_value || 0).toFixed(2)} tone="info" />
                  <Metric label="Actual Release $" value={Number(selectedRow.dependency_actual_release_value || 0).toFixed(2)} tone="info" />
                  <Metric label="Release Delta $" value={Number(selectedRow.dependency_release_delta || 0).toFixed(2)} tone={Number(selectedRow.dependency_release_delta || 0) >= 0 ? "positive" : "warning"} />
                  <Metric label="Dependency Progress %" value={Number(selectedRow.dependency_release_progress_pct || 0).toFixed(1)} tone="info" />
                  <Metric label="Re-sized After Execution" value={selectedRow.resized_after_execution_result ? "Yes" : "No"} tone={selectedRow.resized_after_execution_result ? "warning" : "neutral"} />
                  <Metric label="Original Approved Qty" value={Number(selectedRow.original_approved_order_qty || 0).toFixed(4)} />
                  <Metric label="Recomputed Qty" value={Number(selectedRow.recomputed_approved_order_qty || 0).toFixed(4)} />
                  <Metric label="Recomputed Capital" value={Number(selectedRow.recomputed_capital_approved_value || 0).toFixed(2)} />
                  <Metric label="Recompute Reason" value={selectedRow.recompute_reason || "-"} tone={selectedRow.recompute_reason ? "warning" : "neutral"} />
                  <Metric label="Submission Order" value={selectedRow.submission_order ?? "-"} tone={selectedRow.submission_order ? "positive" : "neutral"} />
                  <Metric label="Retry Eligible" value={selectedRow.retry_eligible ? "Yes" : "No"} tone={selectedRow.retry_eligible ? "warning" : "neutral"} />
                  <Metric label="Retry Reason" value={selectedRow.retry_reason || "-"} tone={selectedRow.retry_reason ? "warning" : "neutral"} />
                  <Metric label="Retry Attempts" value={selectedRow.retry_attempt_count ?? 0} tone="neutral" />
                  <Metric label="Retry Max Attempts" value={selectedRow.retry_max_attempts ?? "-"} tone="neutral" />
                  <Metric label="Retry Next Attempt" value={selectedRow.retry_next_attempt_at || "-"} tone={selectedRow.retry_next_attempt_at ? "warning" : "neutral"} />
                  <Metric label="Backoff Seconds" value={Number(selectedRow.backoff_seconds || 0).toFixed(2)} tone={Number(selectedRow.backoff_seconds || 0) > 0 ? "warning" : "neutral"} />
                  <Metric label="Backoff Strategy" value={selectedRow.backoff_strategy || "-"} tone="neutral" />
                  <Metric label="Retry Exhausted" value={selectedRow.retry_exhausted ? "Yes" : "No"} tone={selectedRow.retry_exhausted ? "negative" : "neutral"} />
                  <Metric label="Permanent Failure" value={selectedRow.permanent_failure ? "Yes" : "No"} tone={selectedRow.permanent_failure ? "negative" : "neutral"} />
                  <Metric label="Current Position %" value={Number(selectedRow.current_position_pct || 0).toFixed(2)} />
                  <Metric label="Target Position %" value={Number(selectedRow.target_position_pct || 0).toFixed(2)} />
                  <Metric label="Autonomous Action" value={selectedRow.autonomous_action || "-"} tone={toneForOutcome(selectedRow.autonomous_action)} />
                  <Metric label="Final Decision Reason" value={selectedRow.final_decision_reason || "-"} tone={selectedRow.final_decision_reason ? "info" : "neutral"} />
                  <Metric label="Session Preferred Action" value={selectedRow.session_preferred_action || "-"} tone={toneForOutcome(selectedRow.session_preferred_action)} />
                  <Metric label="Session Order Plan" value={selectedRow.session_order_plan || "-"} tone={toneForOutcome(selectedRow.session_order_plan)} />
                  <Metric label="Security" value={selectedRow.security_name || selectedRow.symbol || "-"} tone="neutral" />
                  <Metric label="Market Cap Bucket" value={selectedRow.market_cap_bucket || "-"} tone={selectedRow.market_cap_bucket === "small" ? "warning" : "neutral"} />
                  <Metric label="US Equity Eligible" value={selectedRow.us_equity_eligible ? "Yes" : "No"} tone={selectedRow.us_equity_eligible ? "positive" : "warning"} />
                  <Metric label="Listed Exchange" value={selectedRow.listed_exchange || "-"} tone="neutral" />
                  <Metric label="Stock Quality" value={Number(selectedRow.stock_quality_score || 0).toFixed(2)} tone={Number(selectedRow.stock_quality_score || 0) >= 65 ? "positive" : Number(selectedRow.stock_quality_score || 0) >= 50 ? "warning" : "negative"} />
                  <Metric label="Pre-market Score" value={Number(selectedRow.premarket_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Opening Score" value={Number(selectedRow.opening_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Open Confirm Score" value={Number(selectedRow.open_confirmation_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Relative Strength" value={Number(selectedRow.relative_strength_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Sector Strength" value={Number(selectedRow.sector_strength_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Gap Quality" value={Number(selectedRow.gap_quality_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Breakout Quality" value={Number(selectedRow.breakout_quality_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Pullback Quality" value={Number(selectedRow.pullback_quality_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Continuation Score" value={Number(selectedRow.continuation_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Fade Risk" value={Number(selectedRow.fade_risk || 0).toFixed(2)} tone={Number(selectedRow.fade_risk || 0) >= 60 ? "warning" : "neutral"} />
                  <Metric label="Liquidity Score" value={Number(selectedRow.liquidity_score || 0).toFixed(2)} tone="info" />
                  <Metric label="Volatility Risk" value={selectedRow.volatility_risk || "-"} tone={toneForOutcome(selectedRow.volatility_risk)} />
                  <Metric label="Spread Risk" value={selectedRow.spread_risk || "-"} tone={toneForOutcome(selectedRow.spread_risk)} />
                  <Metric label="News Relevance" value={Number(selectedRow.news_relevance_score || 0).toFixed(2)} tone="info" />
                  <Metric label="News Sentiment" value={Number(selectedRow.news_sentiment_score || 0).toFixed(2)} tone={Number(selectedRow.news_sentiment_score || 0) >= 55 ? "positive" : Number(selectedRow.news_sentiment_score || 0) <= 45 ? "negative" : "neutral"} />
                  <Metric label="News Strength" value={Number(selectedRow.news_strength_score || 0).toFixed(2)} tone={Number(selectedRow.news_strength_score || 0) >= 60 ? "positive" : "neutral"} />
                  <Metric label="Catalyst Type" value={selectedRow.catalyst_type || "-"} tone="neutral" />
                  <Metric label="Catalyst Scope" value={selectedRow.catalyst_scope || "-"} tone="neutral" />
                  <Metric label="News Bias" value={selectedRow.news_action_bias || "-"} tone={toneForOutcome(selectedRow.news_action_bias)} />
                  <Metric label="News Requires Wait" value={selectedRow.news_requires_wait ? "Yes" : "No"} tone={selectedRow.news_requires_wait ? "warning" : "neutral"} />
                  <Metric label="News No-trade Reason" value={selectedRow.news_no_trade_reason || "-"} tone={selectedRow.news_no_trade_reason ? "warning" : "neutral"} />
                  <Metric label="Engine Alignment" value={Number(selectedRow.engine_alignment_score || 0).toFixed(2)} tone={Number(selectedRow.engine_alignment_score || 0) >= 70 ? "positive" : Number(selectedRow.engine_alignment_score || 0) >= 55 ? "warning" : "negative"} />
                  <Metric label="Engine Conflict" value={selectedRow.engine_conflicts_present ? selectedRow.engine_conflict_reason || "yes" : "no"} tone={selectedRow.engine_conflicts_present ? "warning" : "positive"} />
                  <Metric label="News Contribution" value={Number(selectedRow.news_contribution_to_score || 0).toFixed(4)} tone="info" />
                  <Metric label="Market Context Contribution" value={Number(selectedRow.market_context_contribution_to_score || 0).toFixed(4)} tone="info" />
                  <Metric label="Addable Value" value={Number(selectedRow.addable_value || 0).toFixed(2)} />
                  <Metric label="Proposed Add Qty" value={Number(selectedRow.proposed_add_qty || 0).toFixed(4)} />
                  <Metric label="Funded" value={selectedRow.funded ? "Yes" : "No"} tone={selectedRow.funded ? "positive" : "warning"} />
                  <Metric label="Funding Status" value={selectedRow.funding_status || "-"} tone={toneForFundingStatus(selectedRow.funding_status)} />
                  <Metric label="Funding Ratio" value={`${(Number(selectedRow.funding_ratio || 0) * 100).toFixed(0)}%`} tone="info" />
                  <Metric label="Funding Decision" value={selectedRow.funding_decision || "-"} tone={toneForOutcome(selectedRow.funding_decision)} />
                  <Metric label="Partial Funding Reason" value={selectedRow.partial_funding_reason || "-"} tone={selectedRow.partial_funding_reason ? "warning" : "neutral"} />
                  <Metric label="Execution Priority" value={selectedRow.execution_priority_band || "-"} tone={toneForPriorityBand(selectedRow.execution_priority_band)} />
                  <Metric label="Capital Requested" value={Number(selectedRow.capital_requested_value || 0).toFixed(2)} />
                  <Metric label="Capital Approved" value={Number(selectedRow.capital_approved_value || 0).toFixed(2)} />
                  <Metric label="Requested Qty" value={Number(selectedRow.requested_order_qty || 0).toFixed(4)} />
                  <Metric label="Approved Qty" value={Number(selectedRow.approved_order_qty || 0).toFixed(4)} />
                  <Metric label="Approved Position %" value={Number(selectedRow.approved_position_pct || 0).toFixed(2)} />
                  <Metric label="Competition Reason" value={selectedRow.capital_competition_reason || "-"} tone={toneForOutcome(selectedRow.capital_competition_reason)} />
                  <Metric label="Better Use Reason" value={selectedRow.better_use_of_capital_reason || "-"} tone="neutral" />
                  <Metric label="Displaced Symbol" value={selectedRow.displaced_symbol || "-"} tone={selectedRow.displaced_symbol ? "warning" : "neutral"} />
                  <Metric label="Rotation Candidate" value={selectedRow.rotation_candidate ? "Yes" : "No"} tone={selectedRow.rotation_candidate ? "warning" : "neutral"} />
                  <Metric label="Rotate From" value={selectedRow.rotation_from_symbol || "-"} tone={selectedRow.rotation_from_symbol ? "warning" : "neutral"} />
                  <Metric label="Rotate To" value={selectedRow.rotation_to_symbol || "-"} tone={selectedRow.rotation_to_symbol ? "positive" : "neutral"} />
                  <Metric label="Capital Preservation" value={selectedRow.capital_preservation_reason || "-"} tone={selectedRow.capital_preservation_reason ? "warning" : "neutral"} />
            <Metric label="ML Signal" value={selectedRow.ml_signal || "-"} tone={toneForComponentContribution(selectedRow.ml_contributed, selectedRow.ml_ready)} />
            <Metric label="ML Contribution" value={Number(selectedRow.ml_contribution_to_score || 0).toFixed(4)} tone={toneForComponentContribution(selectedRow.ml_contributed, selectedRow.ml_ready)} />
            <Metric label="ML Reason Not Used" value={selectedRow.ml_reason_not_used || "-"} tone={selectedRow.ml_reason_not_used ? "warning" : "neutral"} />
            <Metric label="DL Signal" value={selectedRow.dl_signal || "-"} tone={toneForComponentContribution(selectedRow.dl_contributed, selectedRow.dl_ready)} />
            <Metric label="DL Contribution" value={Number(selectedRow.dl_contribution_to_score || 0).toFixed(4)} tone={toneForComponentContribution(selectedRow.dl_contributed, selectedRow.dl_ready)} />
            <Metric label="DL Reason Not Used" value={selectedRow.dl_reason_not_used || "-"} tone={selectedRow.dl_reason_not_used ? "warning" : "neutral"} />
            <Metric label="DL Resolution" value={selectedRow.dl_model_resolution || "-"} tone={selectedRow.dl_fallback_used ? "warning" : "neutral"} />
            <Metric label="Kronos Contribution" value={Number(selectedRow.kronos_contribution_to_score || 0).toFixed(4)} tone={toneForComponentContribution(selectedRow.kronos_contributed, selectedRow.kronos_ready)} />
            <Metric label="Kronos Reason Not Used" value={selectedRow.kronos_reason_not_used || selectedRow.kronos_wait_reason || "-"} tone={selectedRow.kronos_reason_not_used || selectedRow.kronos_wait_reason ? "warning" : "neutral"} />
            <Metric label="Components Used" value={(selectedRow.ensemble_components_used || []).join(", ") || "-"} tone="info" />
            <Metric label="Components Skipped" value={(selectedRow.ensemble_components_skipped || []).join(", ") || "-"} tone="neutral" />
                  <Metric label="Pre-market Submit Reason" value={selectedRow.premarket_submit_reason || "-"} tone={selectedRow.premarket_submit_reason ? "positive" : "neutral"} />
                  <Metric label="Queued For Open Reason" value={selectedRow.queued_for_open_reason || "-"} tone={selectedRow.queued_for_open_reason ? "warning" : "neutral"} />
                  <Metric label="Wait For Open Reason" value={selectedRow.wait_for_open_reason || "-"} tone={selectedRow.wait_for_open_reason ? "warning" : "neutral"} />
                  <Metric label="No-trade Before Open" value={selectedRow.no_trade_before_open_reason || "-"} tone={selectedRow.no_trade_before_open_reason ? "warning" : "neutral"} />
                  <Metric label="Pre-market Allowed" value={selectedRow.premarket_submission_allowed ? "Yes" : "No"} tone={selectedRow.premarket_submission_allowed ? "positive" : "neutral"} />
                  <Metric label="Pre-market Block Reason" value={selectedRow.premarket_submission_block_reason || "-"} tone={selectedRow.premarket_submission_block_reason ? "warning" : "neutral"} />
                  <Metric label="Session Queue Type" value={selectedRow.session_queue_type || "-"} tone="info" />
                  <Metric label="Queue Activation" value={selectedRow.queue_activation_time || "-"} tone="neutral" />
                  <Metric label="Queue Expiration" value={selectedRow.queue_expiration_time || "-"} tone="neutral" />
                  <Metric label="Waiting For Market Open" value={selectedRow.waiting_for_market_open ? "Yes" : "No"} tone={selectedRow.waiting_for_market_open ? "warning" : "neutral"} />
                  <Metric label="Waiting For Revalidation" value={selectedRow.waiting_for_open_revalidation ? "Yes" : "No"} tone={selectedRow.waiting_for_open_revalidation ? "warning" : "neutral"} />
                  <Metric label="Session Go/No-Go" value={selectedRow.session_go_no_go || "-"} tone={toneForOutcome(selectedRow.session_go_no_go)} />
                  <Metric label="Session Gate Result" value={selectedRow.session_gate_result || "-"} tone={toneForOutcome(selectedRow.session_gate_result)} />
                  <Metric label="Session Queue Reason" value={selectedRow.session_queue_reason || "-"} tone={selectedRow.session_queue_reason ? "warning" : "neutral"} />
                  <Metric label="Small-cap Candidate" value={selectedRow.tactical_small_cap_candidate ? "Yes" : "No"} tone={selectedRow.tactical_small_cap_candidate ? "warning" : "neutral"} />
                  <Metric label="Small-cap Score" value={Number(selectedRow.tactical_small_cap_score || 0).toFixed(2)} tone={Number(selectedRow.tactical_small_cap_score || 0) >= 60 ? "positive" : "neutral"} />
                  <Metric label="Small-cap Allowed" value={selectedRow.tactical_small_cap_allowed ? "Yes" : "No"} tone={selectedRow.tactical_small_cap_allowed ? "positive" : "warning"} />
                  <Metric label="Small-cap No-trade" value={selectedRow.small_cap_no_trade_reason || "-"} tone={selectedRow.small_cap_no_trade_reason ? "warning" : "neutral"} />
                  <Metric
                    label="Add Block Reason"
                    value={selectedRow.add_block_reason || "-"}
                    tone={selectedRow.add_block_reason ? toneForOutcome(selectedRow.add_block_reason) : "neutral"}
                  />
                  <Metric label="Why no broker order?" value={selectedBadge?.label || "-"} tone={selectedBadge?.tone || "neutral"} />
                  <Metric label="Reason Group" value={groupMeta(selectedReason?.group || "unknown").label} tone={groupMeta(selectedReason?.group || "unknown").tone} />
                  <Metric label="Broker Submitted" value={selectedRow.broker_order_submitted ? "Yes" : "No"} tone={selectedRow.broker_order_submitted ? "positive" : "neutral"} />
                  <Metric label="Broker Status" value={selectedBrokerStatus.label} tone={selectedBrokerStatus.tone} />
                  <Metric label="Broker Order ID" value={selectedNoBrokerCall ? "-" : selectedRow.broker_order_id || "-"} />
                  <Metric label="Client Order ID" value={selectedNoBrokerCall ? "-" : selectedRow.broker_client_order_id || "-"} />
                  <Metric label="Filled Qty" value={selectedNoBrokerCall ? "-" : selectedRow.filled_qty ?? "-"} />
                  <Metric label="Avg Fill Price" value={selectedNoBrokerCall ? "-" : selectedRow.average_fill_price ?? "-"} />
                </div>

                <div className="info-banner">
                  <b>Reason code:</b> {selectedReason?.code || "-"}<br />
                  <b>Reason description:</b> {selectedReason?.detail || selectedRow.why_no_broker_order_detail || "-"}<br />
                  <b>Decision detail:</b> {selectedRow.decision_outcome_detail || "-"}<br />
                  <b>Guardrail detail:</b> {selectedRow.guardrail_reason_detail || "-"}<br />
                  <b>Outcome detail:</b> {selectedRow.final_outcome_detail || "-"}
                </div>

                <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
                  <div className="settings-row-value" style={{ display: "grid", gap: 8 }}>
                    <div className="cell-muted">Trade Review / Reward / Penalty</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <StatusBadge label={`Review completed: ${selectedRow.trade_review_completed ? "YES" : "NO"}`} tone={selectedRow.trade_review_completed ? "positive" : "warning"} dot={false} />
                      <StatusBadge label={`Trade quality ${Number(selectedRow.trade_quality_score || 0).toFixed(1)}`} tone={Number(selectedRow.trade_quality_score || 0) >= 65 ? "positive" : "warning"} dot={false} />
                      <StatusBadge label={`Timing ${Number(selectedRow.timing_quality_score || 0).toFixed(1)}`} tone="info" dot={false} />
                      <StatusBadge label={`Sizing ${Number(selectedRow.sizing_quality_score || 0).toFixed(1)}`} tone="info" dot={false} />
                      <StatusBadge label={`Capital use ${Number(selectedRow.capital_use_quality_score || 0).toFixed(1)}`} tone="warning" dot={false} />
                      <StatusBadge label={`Reward ${Number(selectedRow.reward_score || 0).toFixed(1)}`} tone="positive" dot={false} />
                      <StatusBadge label={`Penalty ${Number(selectedRow.penalty_score || 0).toFixed(1)}`} tone={Number(selectedRow.penalty_score || 0) > 0 ? "warning" : "neutral"} dot={false} />
                    </div>
                    <div className="cell-muted" style={{ fontSize: 12 }}>
                      {selectedRow.trade_review_summary || "-"}
                    </div>
                    <div className="cell-muted" style={{ fontSize: 12 }}>
                      Lesson: {selectedRow.lesson_learned || "-"} | Behavior hint: {selectedRow.behavior_adjustment_hint || "-"} | Sleeve bias: {selectedRow.sleeve_bias_adjustment || "-"}
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {selectedRewardComponents.length ? selectedRewardComponents.map((item, idx) => (
                        <StatusBadge key={`reward-${idx}`} label={`+ ${item.component}: ${Number(item.score || 0).toFixed(1)}`} tone="positive" dot={false} />
                      )) : <StatusBadge label="No explicit reward component" tone="neutral" dot={false} />}
                      {selectedPenaltyComponents.length ? selectedPenaltyComponents.map((item, idx) => (
                        <StatusBadge key={`penalty-${idx}`} label={`- ${item.component}: ${Number(item.score || 0).toFixed(1)}`} tone="warning" dot={false} />
                      )) : <StatusBadge label="No explicit penalty component" tone="neutral" dot={false} />}
                    </div>
                  </div>

                  <div className="settings-row-value" style={{ display: "grid", gap: 8 }}>
                    <div className="cell-muted">AI Forecast Zone</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <StatusBadge label={`Available: ${selectedRow.ai_forecast_available ? "YES" : "NO"}`} tone={selectedRow.ai_forecast_available ? "positive" : "warning"} dot={false} />
                      <StatusBadge label={`Confidence ${Number(selectedRow.ai_forecast_confidence || 0).toFixed(1)}`} tone={Number(selectedRow.ai_forecast_confidence || 0) >= 65 ? "positive" : "warning"} dot={false} />
                      <StatusBadge label={`Risk ${selectedRow.ai_forecast_risk_level || "-"}`} tone={toneForOutcome(selectedRow.ai_forecast_risk_level)} dot={false} />
                      <StatusBadge label={`Horizon ${selectedRow.ai_forecast_horizon || "-"}`} tone="neutral" dot={false} />
                    </div>
                    <div className="cell-muted" style={{ fontSize: 12 }}>
                      Price {Number(selectedRow.ai_current_price || 0).toFixed(2)} | Base {Number(selectedRow.ai_base_scenario_price || 0).toFixed(2)} | Bull {Number(selectedRow.ai_bullish_scenario_price || 0).toFixed(2)} | Bear {Number(selectedRow.ai_bearish_scenario_price || 0).toFixed(2)}
                    </div>
                    <div className="cell-muted" style={{ fontSize: 12 }}>
                      Range {Number(selectedRow.ai_expected_range_low || 0).toFixed(2)} → {Number(selectedRow.ai_expected_range_high || 0).toFixed(2)} | Support {Number(selectedRow.ai_support_zone_low || 0).toFixed(2)} | Invalidation {Number(selectedRow.ai_invalidation_zone_low || 0).toFixed(2)}
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {selectedForecastChart.length ? selectedForecastChart.map((item, idx) => (
                        <StatusBadge
                          key={`forecast-engine-${idx}`}
                          label={`${item.engine}: ${Number(item.value || 0).toFixed(3)}`}
                          tone={Number(item.value || 0) > 0 ? "positive" : Number(item.value || 0) < 0 ? "warning" : "neutral"}
                          dot={false}
                        />
                      )) : <StatusBadge label={selectedRow.ai_forecast_reason || "No forecast"} tone="neutral" dot={false} />}
                    </div>
                  </div>
                </div>

                {detailLoadingSymbol === selectedRow.symbol ? (
                  <LoadingSkeleton lines={3} />
                ) : (
                  <>
                    {selectedNoBrokerCall ? (
                      <div className="info-banner">
                        <b>No broker call this cycle.</b> سبب التخطي: <b>{selectedRow.execution_skip_reason || "broker_skip_policy"}</b>. أي بيانات وسيط تظهر أدناه تعتبر سياقًا تاريخيًا/سابقًا وليست تنفيذًا حاليًا.
                      </div>
                    ) : (
                      <details>
                        <summary style={{ cursor: "pointer", fontWeight: 600 }}>Broker event timeline (Current cycle)</summary>
                        <pre className="code-block" style={{ marginTop: 8, maxHeight: 220, overflow: "auto" }}>
                          {JSON.stringify(selectedRow.broker_event_timeline || [], null, 2)}
                        </pre>
                      </details>
                    )}

                    {selectedRow.prior_broker_context ? (
                      <details>
                        <summary style={{ cursor: "pointer", fontWeight: 600 }}>Previous/Historical Broker Context</summary>
                        <pre className="code-block" style={{ marginTop: 8, maxHeight: 220, overflow: "auto" }}>
                          {JSON.stringify(selectedRow.prior_broker_context || {}, null, 2)}
                        </pre>
                      </details>
                    ) : null}

                    {selectedRow.historical_position_context ? (
                      <details>
                        <summary style={{ cursor: "pointer", fontWeight: 600 }}>Historical Position Context</summary>
                        <pre className="code-block" style={{ marginTop: 8, maxHeight: 220, overflow: "auto" }}>
                          {JSON.stringify(selectedRow.historical_position_context || {}, null, 2)}
                        </pre>
                      </details>
                    ) : null}

                    <details>
                      <summary style={{ cursor: "pointer", fontWeight: 600 }}>Model/source breakdown (JSON)</summary>
                      <pre className="code-block" style={{ marginTop: 8, maxHeight: 260, overflow: "auto" }}>
                        {JSON.stringify(selectedRow.model_source_breakdown || {}, null, 2)}
                      </pre>
                    </details>
                  </>
                )}
              </div>
            )}
          </SectionCard>
        </>
      )}
    </PageFrame>
  );
}


function Metric({ label, value, tone = "neutral" }) {
  return (
    <div className="settings-row-value" style={{ display: "grid", gap: 4 }}>
      <span className="cell-muted">{label}</span>
      <StatusBadge label={String(value ?? "-")} tone={tone} dot={false} />
    </div>
  );
}
