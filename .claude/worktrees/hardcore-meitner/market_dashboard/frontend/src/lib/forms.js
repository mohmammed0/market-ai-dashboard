import { z } from "zod";


export function parseSymbolList(text) {
  return String(text || "")
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);
}


export const universePresetOptions = [
  { value: "CUSTOM", label: "رموز مخصصة" },
  { value: "NASDAQ", label: "NASDAQ" },
  { value: "NYSE", label: "NYSE" },
  { value: "ALL_US_EQUITIES", label: "جميع الأسهم الأمريكية" },
  { value: "ETF_ONLY", label: "الصناديق المتداولة فقط" },
];


export const universePresetSizeOptions = [25, 50, 100, 150];


export const analyzeSchema = z.object({
  symbol: z.string().min(1, "الرمز مطلوب."),
  startDate: z.string().min(1, "تاريخ البداية مطلوب."),
  endDate: z.string().min(1, "تاريخ النهاية مطلوب."),
});


export const aiNewsSchema = z.object({
  symbol: z.string().optional().default(""),
  headline: z.string().optional().default(""),
  articleText: z.string().optional().default(""),
  itemsText: z.string().optional().default(""),
  marketContext: z.string().optional().default(""),
}).refine((value) => {
  const hasHeadline = Boolean(String(value.headline || "").trim());
  const hasArticle = Boolean(String(value.articleText || "").trim());
  const hasItems = String(value.itemsText || "")
    .split("\n")
    .some((item) => item.trim());
  return hasHeadline || hasArticle || hasItems;
}, {
  message: "أدخل عنواناً أو نص مقال أو خبراً واحداً على الأقل.",
  path: ["headline"],
});


export const symbolListSchema = z.object({
  symbolsText: z.string().min(1, "أدخل رمزاً واحداً على الأقل."),
  startDate: z.string().min(1, "تاريخ البداية مطلوب."),
  endDate: z.string().min(1, "تاريخ النهاية مطلوب."),
}).refine((value) => parseSymbolList(value.symbolsText).length > 0, {
  message: "أدخل رمزاً صحيحاً واحداً على الأقل.",
  path: ["symbolsText"],
});


export const backtestSchema = z.object({
  instrument: z.string().min(1, "الأداة مطلوبة."),
  startDate: z.string().min(1, "تاريخ البداية مطلوب."),
  endDate: z.string().min(1, "تاريخ النهاية مطلوب."),
  holdDays: z.coerce.number().min(1, "يجب أن تكون مدة الاحتفاظ يوماً واحداً على الأقل."),
  minTechnicalScore: z.coerce.number().min(1),
  buyScoreThreshold: z.coerce.number().min(1),
  sellScoreThreshold: z.coerce.number().min(1),
});


export const trainingSchema = z.object({
  symbolsText: z.string().min(1, "أدخل رمزاً واحداً على الأقل."),
  startDate: z.string().min(1, "تاريخ البداية مطلوب."),
  endDate: z.string().min(1, "تاريخ النهاية مطلوب."),
  horizonDays: z.coerce.number().min(1),
  runOptuna: z.boolean().optional().default(false),
});


export const riskPlanSchema = z.object({
  entryPrice: z.coerce.number().positive("يجب أن يكون سعر الدخول موجباً."),
  stopLossPrice: z.union([z.coerce.number().positive(), z.literal("")]).optional().default(""),
  takeProfitPrice: z.union([z.coerce.number().positive(), z.literal("")]).optional().default(""),
  portfolioValue: z.coerce.number().positive("يجب أن تكون قيمة المحفظة موجبة."),
  riskPerTradePct: z.coerce.number().positive(),
  maxDailyLossPct: z.coerce.number().positive(),
});


export const journalSchema = z.object({
  symbol: z.string().min(1, "الرمز مطلوب."),
  strategyMode: z.string().min(1, "الوضع مطلوب."),
  thesis: z.string().min(1, "الفرضية مطلوبة."),
  riskPlan: z.string().min(1, "خطة المخاطر مطلوبة."),
  resultClassification: z.string().min(1, "التصنيف مطلوب."),
  tagsText: z.string().optional().default(""),
  entryReason: z.string().optional().default(""),
  exitReason: z.string().optional().default(""),
  postTradeReview: z.string().optional().default(""),
});


export const strategyEvaluationSchema = z.object({
  instrument: z.string().min(1, "الأداة مطلوبة."),
  startDate: z.string().min(1, "تاريخ البداية مطلوب."),
  endDate: z.string().min(1, "تاريخ النهاية مطلوب."),
  holdDays: z.coerce.number().min(1),
  windows: z.coerce.number().min(2).max(6),
});


export const automationRunSchema = z.object({
  jobName: z.string().min(1, "اسم المهمة مطلوب."),
  preset: z.string().min(1, "الإعداد مطلوب."),
  dryRun: z.boolean().optional().default(true),
});
