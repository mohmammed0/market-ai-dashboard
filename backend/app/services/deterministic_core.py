"""Deterministic Analysis Core.

Wraps existing analysis engines (cached_analysis, risk_engine, explainability)
and maps their output to the canonical typed contracts defined in
``backend.app.domain.platform.contracts``.

No AI or LLM calls are made here.  The output is fully deterministic and
reproducible given the same inputs and the same underlying market data.

Usage
-----
    from backend.app.services.deterministic_core import build_decision_package

    package = build_decision_package("AAPL", "2024-01-01", "2026-04-11")
    # package.stance, package.signal_layer.signal, etc.
"""

from __future__ import annotations

from datetime import date

from backend.app.domain.platform.contracts import (
    AIBiasOverlay,
    ChartMarker,
    DecisionPackage,
    DecisionSurface,
    MarketContext,
    NewsContext,
    NewsItem,
    PriceLevel,
    PriceZone,
    RiskPackage,
    SignalPackage,
)
from backend.app.services.cached_analysis import get_ranked_analysis_result
from backend.app.services.risk_engine import build_trade_risk_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sf(v, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _trend_from_analysis(analysis: dict) -> str:
    signal = str(analysis.get("enhanced_signal") or analysis.get("signal") or "HOLD").upper()
    ts = _sf(analysis.get("technical_score"), 0.0)
    if signal == "BUY" or ts > 20:
        return "up"
    if signal == "SELL" or ts < -20:
        return "down"
    return "sideways"


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------

def _build_market_context(symbol: str, analysis: dict) -> MarketContext:
    close = _sf(analysis.get("close"))
    atr = abs(_sf(analysis.get("atr14"), 0.0))
    return MarketContext(
        symbol=symbol,
        price=close,
        open=_sf(analysis.get("open")) or None,
        high=_sf(analysis.get("high")) or None,
        low=_sf(analysis.get("low")) or None,
        close=close or None,
        volume=_sf(analysis.get("volume")) or None,
        atr=atr or None,
        atr_pct=round(atr / close * 100, 4) if close > 0 and atr > 0 else None,
        support=_sf(analysis.get("support")) or None,
        resistance=_sf(analysis.get("resistance")) or None,
        trend=_trend_from_analysis(analysis),
        date=str(analysis.get("date") or "").split("T")[0] or None,
        data_source="internal",
    )


def _build_signal_package(analysis: dict) -> SignalPackage:
    ml = analysis.get("ml_output") or {}
    dl = analysis.get("dl_output") or {}
    ens = analysis.get("ensemble_output") or {}
    raw_signal = str(analysis.get("enhanced_signal") or analysis.get("signal") or "HOLD").upper()
    if raw_signal not in {"BUY", "SELL", "HOLD"}:
        raw_signal = "HOLD"
    return SignalPackage(
        signal=raw_signal,
        confidence=round(_sf(analysis.get("confidence"), 0.0), 4),
        setup_type=analysis.get("setup_type"),
        best_setup=analysis.get("best_setup"),
        technical_score=_sf(analysis.get("technical_score")) or None,
        mtf_score=_sf(analysis.get("mtf_score")) or None,
        rs_score=_sf(analysis.get("rs_score")) or None,
        trend_quality_score=_sf(analysis.get("trend_quality_score")) or None,
        candle_signal=analysis.get("candle_signal"),
        squeeze_ready=bool(analysis.get("squeeze_ready")),
        ml_signal=(str(ml.get("signal", "")).upper() or None) if ml else None,
        ml_confidence=_sf(ml.get("confidence")) or None,
        dl_signal=(str(dl.get("signal", "")).upper() or None) if dl else None,
        dl_confidence=_sf(dl.get("confidence")) or None,
        ensemble_signal=(str(ens.get("signal", "")).upper() or None) if ens else None,
        ensemble_confidence=_sf(ens.get("confidence")) or None,
        ensemble_reasoning=ens.get("reasoning"),
        mode_used="ensemble" if ens else "classic",
    )


def _build_risk_package(analysis: dict, signal: str) -> RiskPackage:
    close = _sf(analysis.get("close"))
    atr_stop = _sf(analysis.get("atr_stop")) or None
    atr_target = _sf(analysis.get("atr_target")) or None
    support = _sf(analysis.get("support")) or None
    resistance = _sf(analysis.get("resistance")) or None
    stop_price = atr_stop or (support if signal == "BUY" else None)
    target_price = atr_target or (resistance if signal == "BUY" else (support if signal == "SELL" else None))

    risk_plan: dict = {}
    if close > 0:
        try:
            risk_plan = build_trade_risk_plan(
                entry_price=close,
                stop_loss_price=stop_price,
                take_profit_price=target_price,
            )
        except Exception:
            pass

    return RiskPackage(
        entry_price=close or None,
        stop_loss=atr_stop or None,
        take_profit=atr_target or None,
        risk_reward_ratio=_sf(risk_plan.get("reward_risk_ratio")) or _sf(analysis.get("risk_reward")) or None,
        position_size_pct=None,
        max_loss_amount=_sf(risk_plan.get("risk_budget_dollars")) or None,
        suggested_quantity=int(risk_plan.get("suggested_quantity", 0)) or None,
        position_value=_sf(risk_plan.get("position_value")) or None,
        risk_budget_dollars=_sf(risk_plan.get("risk_budget_dollars")) or None,
        invalidation_price=atr_stop or None,
        warnings=risk_plan.get("warnings", []),
    )


def _build_news_context(analysis: dict) -> NewsContext:
    raw_items = analysis.get("news_items") or []
    items = [
        NewsItem(
            title=str(n.get("title") or ""),
            source=n.get("source"),
            published=str(n.get("published") or "").split("T")[0] or None,
            sentiment=n.get("sentiment"),
            url=n.get("url"),
            score=_sf(n.get("score")) or None,
        )
        for n in raw_items[:6]
        if n.get("title")
    ]
    return NewsContext(
        sentiment=analysis.get("ai_news_sentiment") or analysis.get("news_sentiment"),
        score=_sf(analysis.get("ai_news_score") or analysis.get("news_score")) or None,
        summary=analysis.get("ai_summary"),
        items=items,
        ai_generated=bool(analysis.get("ai_summary")),
    )


def _build_decision_surface(
    analysis: dict,
    signal: str,
) -> tuple[DecisionSurface, list[float], float | None]:
    """Build chart surface and return (surface, targets, invalidation)."""
    close = _sf(analysis.get("close"))
    atr = abs(_sf(analysis.get("atr14"), 0.0))
    support = _sf(analysis.get("support")) or None
    resistance = _sf(analysis.get("resistance")) or None
    atr_stop = _sf(analysis.get("atr_stop")) or None
    atr_target = _sf(analysis.get("atr_target")) or None
    analysis_date = str(analysis.get("date") or "").split("T")[0] or None

    zones: list[PriceZone] = []
    levels: list[PriceLevel] = []
    markers: list[ChartMarker] = []
    targets: list[float] = []
    invalidation: float | None = atr_stop

    if close > 0:
        # Derive entry and target zones from signal + technical levels
        if signal == "BUY":
            ent_lo = support if support else close - atr * 0.4
            ent_hi = close
            tgt_lo = close + atr * 0.35
            tgt_hi = resistance if resistance else (atr_target if atr_target else close + atr * 1.2)
        elif signal == "SELL":
            ent_lo = close
            ent_hi = resistance if resistance else close + atr * 0.4
            tgt_lo = support if support else close - atr * 1.2
            tgt_hi = close - atr * 0.35
        else:
            ent_lo = close - atr * 0.25
            ent_hi = close + atr * 0.25
            tgt_lo = support if support else close - atr * 0.5
            tgt_hi = resistance if resistance else close + atr * 0.5

        # Normalise
        ent_lo, ent_hi = min(ent_lo, ent_hi), max(ent_lo, ent_hi)
        if ent_hi > ent_lo:
            tone = "accent" if signal == "BUY" else "warning" if signal == "SELL" else "subtle"
            zones.append(PriceZone(
                kind="entry_zone",
                label="منطقة الدخول",
                tone=tone,
                low=round(ent_lo, 4),
                high=round(ent_hi, 4),
                source="derived_from_support_resistance_atr",
            ))

        if tgt_lo is not None and tgt_hi is not None:
            t_lo, t_hi = min(tgt_lo, tgt_hi), max(tgt_lo, tgt_hi)
            if t_hi > t_lo:
                zones.append(PriceZone(
                    kind="target_zone",
                    label="منطقة الهدف",
                    tone="positive",
                    low=round(t_lo, 4),
                    high=round(t_hi, 4),
                    source="derived_from_resistance_support_atr_target",
                ))
                targets = [round((t_lo + t_hi) / 2, 4)]

        # Signal marker
        tone = "positive" if signal == "BUY" else "negative" if signal == "SELL" else "subtle"
        markers.append(ChartMarker(
            kind="signal_marker",
            label=signal,
            tone=tone,
            date=analysis_date,
            value=round(close, 4),
            detail=analysis.get("setup_type") or analysis.get("reasons") or signal,
        ))

    # Horizontal levels
    for kind, label, value, tone in [
        ("support", "الدعم", support, "subtle"),
        ("resistance", "المقاومة", resistance, "warning"),
        ("invalidation", "الإبطال / الوقف", atr_stop, "negative"),
        ("target", "هدف ATR", atr_target, "positive"),
    ]:
        if value is not None and value > 0:
            levels.append(PriceLevel(kind=kind, label=label, value=round(value, 4), tone=tone))

    # News markers (top 3)
    for n in (analysis.get("news_items") or [])[:3]:
        pub = str(n.get("published") or "").split("T")[0] or None
        sent = str(n.get("sentiment") or "").upper()
        ntone = "positive" if sent in {"BUY", "BULLISH", "POSITIVE"} else "negative" if sent in {"SELL", "BEARISH", "NEGATIVE"} else "subtle"
        markers.append(ChartMarker(
            kind="news_marker",
            label=n.get("source") or "خبر",
            tone=ntone,
            date=pub,
            value=round(close, 4) if close > 0 else None,
            detail=n.get("title"),
        ))

    surface = DecisionSurface(
        zones=zones,
        levels=levels,
        markers=markers[:8],
        note="المناطق والمستويات مشتقة من التحليل الفني الحتمي وليست توصية مستقلة.",
    )
    return surface, targets, invalidation


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_decision_package(
    symbol: str,
    start_date: str = "2024-01-01",
    end_date: str | None = None,
    *,
    include_dl: bool = True,
    include_ensemble: bool = True,
) -> DecisionPackage:
    """Build the canonical DecisionPackage using deterministic analysis only.

    The ``ai_layer`` is populated with a deterministic rule-based explanation
    (from ``explainability.build_signal_explanation``).  The caller can
    subsequently enrich the package with an LLM overlay via
    ``ai_overlay.enrich_with_ai_overlay(package)``.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "AAPL").
    start_date, end_date : str
        Date range for the analysis window.
    include_dl, include_ensemble : bool
        Whether to run DL inference and ensemble voting.
    """
    resolved_end = end_date or date.today().isoformat()

    analysis = get_ranked_analysis_result(
        symbol,
        start_date,
        resolved_end,
        include_ml=True,
        include_dl=include_dl,
        ttl_seconds=300,
    )

    raw_signal = str(analysis.get("enhanced_signal") or analysis.get("signal") or "HOLD").upper()
    signal: str = raw_signal if raw_signal in {"BUY", "SELL", "HOLD"} else "HOLD"

    # Build each layer
    market_ctx = _build_market_context(symbol, analysis)
    signal_pkg = _build_signal_package(analysis)
    risk_pkg = _build_risk_package(analysis, signal)
    news_ctx = _build_news_context(analysis)
    surface, targets, invalidation = _build_decision_surface(analysis, signal)

    # Deterministic AI layer — rule-based explanation, no LLM
    from backend.app.services.explainability import build_signal_explanation  # noqa: PLC0415
    expl = build_signal_explanation(analysis)
    bias = "bullish" if signal == "BUY" else "bearish" if signal == "SELL" else "neutral"
    ai_layer = AIBiasOverlay(
        bias=bias,
        confidence=round(_sf(analysis.get("confidence"), 0.0), 2),
        explanation=expl.get("summary"),
        supporting_factors=expl.get("supporting_factors", []),
        contradictions=expl.get("contradictory_factors", []),
        caveats=expl.get("invalidators", []),
        news_summary=analysis.get("ai_summary"),
        source="deterministic",
    )

    # Evidence — key facts used to reach the stance
    evidence: list[str] = (expl.get("supporting_factors", [])[:3] + [
        f"Signal: {signal_pkg.signal} @ {signal_pkg.confidence:.0f}% confidence",
    ])

    return DecisionPackage(
        symbol=symbol,
        price_layer=market_ctx,
        signal_layer=signal_pkg,
        risk_layer=risk_pkg,
        ai_layer=ai_layer,
        news_layer=news_ctx,
        chart_surface=surface,
        stance=signal,
        confidence=signal_pkg.confidence,
        evidence=evidence,
        targets=targets,
        invalidation=invalidation,
        rationale=(
            (analysis.get("ensemble_output") or {}).get("reasoning")
            or analysis.get("reasons")
            or expl.get("summary")
        ),
        deterministic_only=True,
    )
