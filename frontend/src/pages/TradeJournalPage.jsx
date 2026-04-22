import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/ui/PageFrame";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchJournalEntries, saveJournalEntry } from "../lib/api";
import { journalSchema } from "../lib/forms";
import { t } from "../lib/i18n";


function parseTags(text) {
  return String(text || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}


export default function TradeJournalPage() {
  const [journal, setJournal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(journalSchema),
    defaultValues: {
      symbol: "AAPL",
      strategyMode: "classic",
      thesis: "",
      riskPlan: "",
      resultClassification: "good_process",
      tagsText: "",
      entryReason: "",
      exitReason: "",
      postTradeReview: "",
    },
  });

  async function loadEntries() {
    setLoading(true);
    try {
      setJournal(await fetchJournalEntries({ limit: 100 }));
    } catch (requestError) {
      setError(requestError.message || "Trade journal failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadEntries();
  }, []);

  async function onSubmit(values) {
    setSubmitting(true);
    setError("");
    try {
      await saveJournalEntry({
        symbol: values.symbol.trim().toUpperCase(),
        strategy_mode: values.strategyMode,
        thesis: values.thesis,
        risk_plan: values.riskPlan,
        result_classification: values.resultClassification,
        tags: parseTags(values.tagsText),
        entry_reason: values.entryReason,
        exit_reason: values.exitReason,
        post_trade_review: values.postTradeReview,
      });
      reset({
        ...values,
        thesis: "",
        riskPlan: "",
        tagsText: "",
        entryReason: "",
        exitReason: "",
        postTradeReview: "",
      });
      await loadEntries();
    } catch (requestError) {
      setError(requestError.message || "Saving trade journal entry failed.");
    } finally {
      setSubmitting(false);
    }
  }

  const columns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "strategy_mode", header: "Mode" },
      { accessorKey: "result_classification", header: "Classification" },
      { accessorKey: "thesis", header: "Thesis" },
      { accessorKey: "risk_plan", header: "Risk Plan" },
      { accessorKey: "post_trade_review", header: "Review" },
    ],
    []
  );

  const summaryItems = Object.entries(journal?.classification_counts || {}).map(([label, value]) => ({
    label: label.replaceAll("_", " "),
    value,
  }));

  return (
    <PageFrame
      title="Trade Journal"
      description="Capture thesis, risk plan, process quality, and post-trade reviews tied to the current trading workflow."
      eyebrow="Journal + Feedback"
      headerActions={<StatusBadge label="Review Loop" tone="accent" />}
    >
      <FilterBar
        title="Journal Entry"
        description="Add structured process notes so trading results can feed future evaluation and model reviews."
        action={<StatusBadge label={submitting ? "Saving" : "Journal Ready"} tone={submitting ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid">
            <label className="field">
              <span>{t("Symbol")}</span>
              <input {...register("symbol")} />
              {errors.symbol ? <small className="field-error">{errors.symbol.message}</small> : null}
            </label>
            <label className="field">
              <span>{t("Mode")}</span>
              <select {...register("strategyMode")}>
                <option value="classic">كلاسيكي</option>
                <option value="vectorbt">VectorBT</option>
                <option value="ml">ML</option>
                <option value="dl">DL</option>
                <option value="ensemble">تجميعي</option>
              </select>
            </label>
            <label className="field">
              <span>{t("Classification")}</span>
              <select {...register("resultClassification")}>
                <option value="good_process">تنفيذ جيد</option>
                <option value="bad_process">تنفيذ سيئ</option>
                <option value="lucky_win">ربح محظوظ</option>
                <option value="avoidable_loss">خسارة كان يمكن تجنبها</option>
              </select>
            </label>
            <label className="field field-span-2">
              <span>{t("Thesis")}</span>
              <textarea className="field-textarea" {...register("thesis")} />
            </label>
            <label className="field field-span-2">
              <span>{t("Risk Plan")}</span>
              <textarea className="field-textarea" {...register("riskPlan")} />
            </label>
            <label className="field">
              <span>{t("Entry Reason")}</span>
              <input {...register("entryReason")} />
            </label>
            <label className="field">
              <span>{t("Exit Reason")}</span>
              <input {...register("exitReason")} />
            </label>
            <label className="field">
              <span>{t("Tags")}</span>
              <input {...register("tagsText")} placeholder="سوينغ، اختراق، نتائج" />
            </label>
            <label className="field field-span-2">
              <span>{t("Post-Trade Review")}</span>
              <textarea className="field-textarea" {...register("postTradeReview")} />
            </label>
          </div>
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "جارٍ الحفظ..." : "حفظ التدوينة"}
            </button>
          </div>
          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      <div className="panel result-panel">
        <SectionHeader title="Journal Summary" description="Process-quality breakdown from the current trade-journal history." />
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : summaryItems.length ? (
          <SummaryStrip items={summaryItems} />
        ) : (
          <div className="empty-state compact-empty">
            <strong>{t("No journal entries yet")}</strong>
            <p>{t("Add your first thesis and review to start building a feedback loop.")}</p>
          </div>
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader title="Journal History" description="Structured notes for reviewing process quality over time." />
        {loading ? (
          <LoadingSkeleton lines={7} />
        ) : (
          <DataTable
            columns={columns}
            data={journal?.items || []}
            emptyTitle="No journal entries"
            emptyDescription="Entries will appear here after you save a trade review."
          />
        )}
      </div>
    </PageFrame>
  );
}
