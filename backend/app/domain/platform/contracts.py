"""Canonical platform contracts.

These typed Pydantic models define the structured data contracts used
across the platform's deterministic analysis, AI overlay, execution,
and simulation layers.

Design principles
-----------------
- Deterministic facts (price, signals, risk) are ALWAYS separate from
  AI overlay (bias, explanation, LLM summaries).
- Every execution-facing contract is isolated from AI-facing contracts.
  The AI layer MUST NOT trigger execution paths.
- Schema version is embedded for forward compatibility.
- All contracts are importable from ``backend.app.domain.platform``.

schema_version: "1.0"
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Market / Price Layer
# ---------------------------------------------------------------------------


class MarketContext(BaseModel):
    """Deterministic price and market structure data (price layer)."""

    symbol: str
    price: float = Field(default=0.0, ge=0.0)
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    atr: float | None = None
    atr_pct: float | None = None
    support: float | None = None
    resistance: float | None = None
    trend: Literal["up", "down", "sideways", "unknown"] = "unknown"
    date: str | None = None
    data_source: str = "internal"


# ---------------------------------------------------------------------------
# Signal Layer
# ---------------------------------------------------------------------------


class SignalPackage(BaseModel):
    """Deterministic signal data from all analysis modes (signal layer)."""

    signal: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    setup_type: str | None = None
    best_setup: str | None = None
    technical_score: float | None = None
    mtf_score: float | None = None
    rs_score: float | None = None
    trend_quality_score: float | None = None
    candle_signal: str | None = None
    squeeze_ready: bool = False
    ml_signal: str | None = None
    ml_confidence: float | None = None
    dl_signal: str | None = None
    dl_confidence: float | None = None
    ensemble_signal: str | None = None
    ensemble_confidence: float | None = None
    ensemble_reasoning: str | None = None
    mode_used: str = "classic"


# ---------------------------------------------------------------------------
# Risk Layer
# ---------------------------------------------------------------------------


class RiskPackage(BaseModel):
    """Deterministic risk plan from the risk engine (risk layer)."""

    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward_ratio: float | None = None
    position_size_pct: float | None = None
    max_loss_amount: float | None = None
    suggested_quantity: int | None = None
    position_value: float | None = None
    risk_budget_dollars: float | None = None
    invalidation_price: float | None = None
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# News Layer
# ---------------------------------------------------------------------------


class NewsItem(BaseModel):
    """A single news item."""

    title: str
    source: str | None = None
    published: str | None = None
    sentiment: str | None = None
    url: str | None = None
    score: float | None = None


class NewsContext(BaseModel):
    """News and sentiment context (news layer)."""

    sentiment: str | None = None
    score: float | None = None
    summary: str | None = None
    items: list[NewsItem] = Field(default_factory=list)
    ai_generated: bool = False  # True if summary was produced by an LLM


# ---------------------------------------------------------------------------
# AI Overlay Layer
# ---------------------------------------------------------------------------


class AIBiasOverlay(BaseModel):
    """AI-generated explanation overlay (AI bias/confidence layer).

    This layer is ALWAYS separate from deterministic analysis.
    It is advisory and explanatory only.
    AI MUST NOT trigger execution through this layer.
    """

    bias: Literal["bullish", "bearish", "neutral"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=100.0)
    explanation: str | None = None
    supporting_factors: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    news_summary: str | None = None
    source: Literal["deterministic", "ollama", "openai", "fallback"] = "deterministic"  # openai kept for backward compat with stored data
    model_used: str | None = None
    generated_at: str | None = None


# ---------------------------------------------------------------------------
# Decision Surface / Chart Layer
# ---------------------------------------------------------------------------


class PriceZone(BaseModel):
    """A price zone for chart rendering (entry, target, support, resistance)."""

    kind: str  # "entry_zone" | "target_zone" | "support_zone" | "resistance_zone"
    label: str
    tone: str  # "accent" | "positive" | "negative" | "warning" | "subtle"
    low: float
    high: float
    source: str
    confidence: float | None = None


class PriceLevel(BaseModel):
    """A single horizontal price level line."""

    kind: str  # "support" | "resistance" | "invalidation" | "target"
    label: str
    value: float
    tone: str


class ChartMarker(BaseModel):
    """A chart marker (signal, news event, calendar event)."""

    kind: str  # "signal_marker" | "news_marker" | "event_marker"
    label: str
    tone: str
    date: str | None = None
    value: float | None = None
    detail: str | None = None


class DecisionSurface(BaseModel):
    """Structured chart output contract: zones + levels + markers."""

    zones: list[PriceZone] = Field(default_factory=list)
    levels: list[PriceLevel] = Field(default_factory=list)
    markers: list[ChartMarker] = Field(default_factory=list)
    note: str | None = None


# ---------------------------------------------------------------------------
# Decision Package (full layered output)
# ---------------------------------------------------------------------------


class DecisionPackage(BaseModel):
    """Structured layered decision output — the canonical chart/decision contract.

    Layers
    ------
    price_layer      Market context / OHLCV / support-resistance
    signal_layer     Deterministic signals (classic + ML + DL + ensemble)
    risk_layer       Risk plan (entry / stop / target / position sizing)
    ai_layer         AI explanation overlay — advisory only, non-executable
    news_layer       News sentiment and items
    chart_surface    Zones / levels / markers for chart rendering

    Outputs
    -------
    stance           BUY / SELL / HOLD
    confidence       0-100
    evidence         Key evidence strings
    targets          Price target(s)
    invalidation     Invalidation / stop price
    rationale        Human-readable rationale string

    The ``deterministic_only`` flag is True when no AI overlay was applied.
    """

    symbol: str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    schema_version: str = "1.0"

    # Layers
    price_layer: MarketContext
    signal_layer: SignalPackage
    risk_layer: RiskPackage
    ai_layer: AIBiasOverlay
    news_layer: NewsContext
    chart_surface: DecisionSurface

    # Actionable summary outputs
    stance: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    evidence: list[str] = Field(default_factory=list)
    targets: list[float] = Field(default_factory=list)
    invalidation: float | None = None
    rationale: str | None = None

    # Metadata
    deterministic_only: bool = False


# ---------------------------------------------------------------------------
# Execution Layer Contracts
# ---------------------------------------------------------------------------


class ExecutionIntentContract(BaseModel):
    """Structured execution intent — before confirmation step."""

    intent: Literal["OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT", "NONE"]
    symbol: str
    strategy_mode: str
    side: str | None = None
    quantity: float = Field(default=0.0, ge=0.0)
    reference_price: float = Field(default=0.0, ge=0.0)
    reason: str = ""
    risk_checked: bool = False


class ExecutionPreview(BaseModel):
    """Read-only execution preview returned before the confirm step.

    The preview is non-binding. No trade is executed until /execution/confirm
    is called with the preview_id.

    ``trace_id`` chains the preview → confirm → order audit events together.
    """

    preview_id: str
    trace_id: str | None = None
    symbol: str
    side: str  # "BUY" | "SELL"
    quantity: float
    order_type: str = "market"
    reference_price: float
    estimated_fill_price: float
    estimated_fee: float
    estimated_slippage: float
    estimated_spread: float
    estimated_total_cost: float
    halt_status: dict[str, Any] = Field(default_factory=dict)
    risk_check: dict[str, Any] = Field(default_factory=dict)
    is_safe_to_execute: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fill_preview: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: str | None = None


class ExecutionConfirmResult(BaseModel):
    """Result returned from the /execution/confirm step.

    ``trace_id`` links this confirmation back to its preview and forward to
    the order creation audit event, forming an inspectable chain:
    preview(trace_id) → confirm(trace_id) → order_created(correlation_id=trace_id).
    """

    order_id: int | None = None
    client_order_id: str
    preview_id: str
    trace_id: str | None = None
    symbol: str
    status: str  # "FILLED" | "PARTIAL_FILL" | "REJECTED" | "HALTED"
    fill_price: float | None = None
    filled_quantity: float | None = None
    fee: float | None = None
    is_partial: bool = False
    blocked_reason: str | None = None
    audit_correlation_id: str
    confirmed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Simulation Fill Details
# ---------------------------------------------------------------------------


class SimulationFillDetails(BaseModel):
    """Formalized fill details — corresponds to paper_fill_engine.FillResult."""

    reference_price: float
    spread_adj: float
    slippage_adj: float
    fee_amount: float
    fill_price: float
    filled_quantity: float
    fill_ratio: float
    is_partial: bool
    order_type: str
    side: str


# ---------------------------------------------------------------------------
# Strategy Lab / Experiment Contracts
# ---------------------------------------------------------------------------


class WalkForwardWindow(BaseModel):
    """A single time window in a walk-forward validation run."""

    window: int
    start_date: str
    end_date: str
    classic_total_return_pct: float = 0.0
    classic_win_rate_pct: float = 0.0
    vectorbt_total_return_pct: float = 0.0
    vectorbt_max_drawdown_pct: float = 0.0


class OverfittingMetrics(BaseModel):
    """Out-of-sample / overfitting health metrics."""

    train_return_pct: float
    oos_avg_return_pct: float
    oos_decay_pct: float        # (train - oos) / max(|train|, 1) * 100
    win_rate_stability: float   # stddev of window win_rates (lower is better)
    overfit_flag: bool          # True if decay > 40% or stability > 20 stddev
    overfit_score: float        # 0–100 (100 = perfect stability)
    note: str | None = None


class StrategyLabRigorResult(BaseModel):
    """Full strategy lab result including walk-forward and overfitting metrics."""

    run_id: str
    instrument: str
    seed: int | None = None
    config_hash: str | None = None
    leaderboard: list[dict[str, Any]] = Field(default_factory=list)
    walk_forward: list[WalkForwardWindow] = Field(default_factory=list)
    overfitting: OverfittingMetrics | None = None
    best_strategy: str | None = None
    experiment_tracked: bool = False
    experiment_run_id: str | None = None
    experiment_backend: str | None = None


# ---------------------------------------------------------------------------
# Audit Event Payload Shapes
# ---------------------------------------------------------------------------


class AuditEventShape(BaseModel):
    """Base shape for structured audit event payloads."""

    event_type: str
    symbol: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class FillAuditPayload(BaseModel):
    """Standard shape for fill-related audit event payloads."""

    price: float
    quantity: float
    realized_pnl: float | None = None
    fill: SimulationFillDetails | None = None


class HaltAuditPayload(BaseModel):
    """Standard shape for halt-event audit payloads."""

    halted: bool
    reason: str | None = None
    enabled_by: str | None = None


class RiskGateAuditPayload(BaseModel):
    """Standard shape for risk-gate blocked event payloads."""

    intent: str
    blocked_reason: str
    price: float
    quantity: float
    warnings: list[str] = Field(default_factory=list)
