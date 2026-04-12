import EmptyState from "./EmptyState";
import ErrorBanner from "./ErrorBanner";
import LoadingSkeleton from "./LoadingSkeleton";
import SectionCard from "./SectionCard";
import StatusBadge from "./StatusBadge";
import { translateNode } from "../../lib/i18n";


function toneForSignal(value) {
  const normalized = String(value || "").trim().toUpperCase();
  if (normalized === "BUY" || normalized === "BULLISH") return "positive";
  if (normalized === "SELL" || normalized === "BEARISH") return "negative";
  if (normalized === "HOLD" || normalized === "NEUTRAL") return "warning";
  return "neutral";
}

function listOrFallback(items, fallback) {
  return items?.length ? items : [fallback];
}

function AiOverlayBadge({ provenance }) {
  if (!provenance) return null;
  const isAi = provenance.ai_overlay_applied || provenance.ai_source === "openai";
  const source = provenance.ai_source || "deterministic";
  const model = provenance.ai_model;

  return (
    <div className="ai-overlay-badge" data-active={isAi}>
      <span className={`ai-overlay-dot ai-overlay-dot--${isAi ? "active" : source === "fallback" ? "fallback" : "deterministic"}`} />
      <span className="ai-overlay-label">
        {isAi ? "AI نشط" : source === "fallback" ? "AI احتياطي" : "حتمي فقط"}
      </span>
      {model && <span className="ai-overlay-model">{model}</span>}
    </div>
  );
}


export default function DecisionPanel({
  decision,
  loading = false,
  error = "",
  title = "لوحة القرار",
  description = "الموقف، الأدلة، والمخاطر.",
  className = "",
}) {
  const strategyHook = decision?.strategy_hooks?.latest_evaluation;
  const candidateHook = decision?.strategy_hooks?.generated_candidate;
  const backtestHook = decision?.backtest_hooks || {};
  const news = decision?.news || {};
  const provenance = decision?.provenance;
  const aiLayer = decision?.decision_package?.ai_layer;

  return (
    <SectionCard
      title={title}
      description={description}
      className={className}
      action={
        <StatusBadge
          label={decision?.stance || "WAIT"}
          tone={toneForSignal(decision?.stance)}
        />
      }
    >
      <ErrorBanner message={error} />

      {loading ? (
        <LoadingSkeleton lines={8} />
      ) : decision ? (
        <div className="decision-panel">
          {/* Stance & Confidence */}
          <div className="decision-stance">
            <div style={{ flex: 1 }}>
              <div className="decision-stance-label">الموقف</div>
              <div className={`decision-stance-value text-${toneForSignal(decision.stance) === "positive" ? "positive" : toneForSignal(decision.stance) === "negative" ? "negative" : "warning"}`}>
                {decision.stance || "HOLD"}
              </div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div className="decision-stance-label">الثقة</div>
              <div className="decision-stance-value">{decision.confidence ?? "-"}%</div>
            </div>
            <div style={{ textAlign: "end" }}>
              <div className="decision-stance-label">الإعداد</div>
              <div className="decision-stance-value text-sm font-medium">{decision.best_setup || "-"}</div>
            </div>
          </div>

          {/* Confidence bar */}
          {decision.confidence != null && (
            <div className="progress-bar">
              <div
                className={`progress-bar-fill progress-bar-fill--${toneForSignal(decision.stance) === "positive" ? "positive" : toneForSignal(decision.stance) === "negative" ? "negative" : "warning"}`}
                style={{ width: `${Math.min(100, Math.max(0, decision.confidence))}%` }}
              />
            </div>
          )}

          {/* AI Overlay Status */}
          <AiOverlayBadge provenance={provenance} />

          {/* AI Overlay Explanation (when AI is active) */}
          {aiLayer && aiLayer.source !== "deterministic" && aiLayer.explanation && (
            <div className="ai-overlay-explanation">
              <div className="ai-overlay-explanation-header">
                <span className="ai-overlay-explanation-icon">✦</span>
                <span>تحليل الذكا�� الاصطناعي</span>
                {aiLayer.confidence != null && (
                  <span className="ai-overlay-confidence">ثقة AI: {Math.round(aiLayer.confidence)}%</span>
                )}
              </div>
              <p className="ai-overlay-explanation-text">{aiLayer.explanation}</p>
              {aiLayer.news_summary && (
                <p className="ai-overlay-news-summary">
                  <strong>الأخبار:</strong> {aiLayer.news_summary}
                </p>
              )}
              {aiLayer.contradictions?.length > 0 && (
                <div className="ai-overlay-contradictions">
                  <span className="decision-section-title">تحفظات AI</span>
                  <div className="decision-evidence-list">
                    {aiLayer.contradictions.map((c, i) => (
                      <span className="decision-evidence-chip" key={i} style={{ borderColor: "rgba(245,158,11,0.25)", background: "rgba(245,158,11,0.06)" }}>{c}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Rationale (deterministic) */}
          {decision.rationale && (
            <div className="info-banner">{decision.rationale}</div>
          )}

          {/* Evidence */}
          {decision.evidence?.length > 0 && (
            <div className="decision-section">
              <span className="decision-section-title">الأدلة الرئيسية</span>
              <div className="decision-evidence-list">
                {decision.evidence.map((item, i) => (
                  <span className="decision-evidence-chip" key={i}>{item}</span>
                ))}
              </div>
            </div>
          )}

          {/* Targets */}
          {(decision.targets || backtestHook.atr_target || backtestHook.atr_stop) && (
            <div className="decision-section">
              <span className="decision-section-title">الأهداف</span>
              <div className="decision-targets">
                {decision.targets?.map((t, i) => (
                  <div className="decision-target-item" key={i}>
                    <div className="decision-target-label">{t.label || `هدف ${i + 1}`}</div>
                    <div className="decision-target-value text-positive">{t.price ?? t.value ?? "-"}</div>
                  </div>
                ))}
                {backtestHook.atr_target && (
                  <div className="decision-target-item">
                    <div className="decision-target-label">ATR Target</div>
                    <div className="decision-target-value text-positive">{backtestHook.atr_target}</div>
                  </div>
                )}
                {backtestHook.atr_stop && (
                  <div className="decision-target-item">
                    <div className="decision-target-label">ATR Stop</div>
                    <div className="decision-target-value text-negative">{backtestHook.atr_stop}</div>
                  </div>
                )}
                {backtestHook.risk_reward && (
                  <div className="decision-target-item">
                    <div className="decision-target-label">R/R</div>
                    <div className="decision-target-value">{backtestHook.risk_reward}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Factors */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
            <div className="decision-section">
              <span className="decision-section-title">عوامل داعمة</span>
              <div className="decision-evidence-list">
                {listOrFallback(decision.bullish_factors, "لا يوجد").map((f, i) => (
                  <span className="decision-evidence-chip" key={i} style={{ borderColor: "rgba(16,185,129,0.2)", background: "rgba(16,185,129,0.06)" }}>{f}</span>
                ))}
              </div>
            </div>
            <div className="decision-section">
              <span className="decision-section-title">عوامل ضاغطة</span>
              <div className="decision-evidence-list">
                {listOrFallback(decision.bearish_factors, "لا يوجد").map((f, i) => (
                  <span className="decision-evidence-chip" key={i} style={{ borderColor: "rgba(239,68,68,0.2)", background: "rgba(239,68,68,0.06)" }}>{f}</span>
                ))}
              </div>
            </div>
          </div>

          {/* Risks */}
          {decision.risks?.length > 0 && (
            <div className="decision-section">
              <span className="decision-section-title">المخاطر</span>
              <div className="decision-evidence-list">
                {decision.risks.map((r, i) => (
                  <span className="decision-evidence-chip" key={i} style={{ borderColor: "rgba(245,158,11,0.2)", background: "rgba(245,158,11,0.06)" }}>{r}</span>
                ))}
              </div>
            </div>
          )}

          {/* Provenance */}
          {provenance && (
            <div className="decision-section">
              <span className="decision-section-title">مصدر البيانات</span>
              <div className="provenance-strip">
                {Object.entries(provenance)
                  .filter(([k]) => !["deterministic_only", "ai_overlay_applied", "ai_source", "ai_model", "ai_generated_at"].includes(k))
                  .map(([key, val]) => (
                    <span
                      key={key}
                      className={`provenance-tag provenance-tag--${val === "deterministic" ? "deterministic" : val === "ai_enriched" ? "ai" : "tool"}`}
                    >
                      {key.replace("_layer", "").replace("_surface", "")}: {val}
                    </span>
                  ))}
              </div>
            </div>
          )}

          {/* News (deterministic / fallback) */}
          {news.summary && !aiLayer?.news_summary && (
            <div className="status-message info" style={{ fontSize: "var(--text-xs)" }}>
              {news.summary}
            </div>
          )}

          {/* Strategy hooks */}
          {(strategyHook || candidateHook) && (
            <div className="decision-section">
              <span className="decision-section-title">ارتباط الاستراتيجية</span>
              <div className="decision-targets">
                {strategyHook?.best_strategy && (
                  <div className="decision-target-item">
                    <div className="decision-target-label">أفضل استراتيجية</div>
                    <div className="decision-target-value">{strategyHook.best_strategy}</div>
                  </div>
                )}
                {candidateHook?.candidate_name && (
                  <div className="decision-target-item">
                    <div className="decision-target-label">مرشح مستمر</div>
                    <div className="decision-target-value">{candidateHook.candidate_name}</div>
                  </div>
                )}
                {candidateHook?.score != null && (
                  <div className="decision-target-item">
                    <div className="decision-target-label">درجة المرشح</div>
                    <div className="decision-target-value">{candidateHook.score}</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        <EmptyState
          title="لا توجد طبقة قرار"
          description="عند توفر القرار المهيكل ستظهر الإشارة والثقة والعوامل."
        />
      )}
    </SectionCard>
  );
}
