"""AI Coordinator / Overlay Layer.

Consumes a deterministic ``DecisionPackage`` and enriches the ``ai_layer``
using an LLM (OpenAI) when available.  Falls back silently to the
deterministic explanation already embedded in the package if:

- OpenAI is not configured
- The API call fails or times out
- The response is malformed

Design rules
------------
- AI MUST NOT trigger execution paths.
- All AI-facing data queries go through the ToolGateway.
- The deterministic layers (price, signal, risk) are NEVER modified.
- This module only ever replaces ``ai_layer`` on the package.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from backend.app.core.logging_utils import get_logger, log_event
from backend.app.domain.platform.contracts import AIBiasOverlay, DecisionPackage
from backend.app.services.tool_gateway import get_tool_gateway

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Overlay status tracking (module-level, thread-safe via GIL for counters)
# ---------------------------------------------------------------------------

_overlay_stats: dict = {
    "total_calls": 0,
    "success_count": 0,
    "fallback_count": 0,
    "failure_count": 0,
    "last_success_at": None,
    "last_failure_at": None,
    "last_failure_reason": None,
    "last_model_used": None,
    "last_latency_seconds": None,
    "avg_latency_seconds": 0.0,
    "_latency_samples": [],
}


def get_overlay_status() -> dict:
    """Return current AI overlay runtime status for observability."""
    try:
        from backend.app.services.llm_gateway import get_llm_status
        llm_status = get_llm_status()
    except Exception:
        llm_status = {"effective_status": "error", "effective_provider": None}

    total = _overlay_stats["total_calls"]
    return {
        "llm_status": llm_status,
        "overlay_total_calls": total,
        "overlay_success_count": _overlay_stats["success_count"],
        "overlay_fallback_count": _overlay_stats["fallback_count"],
        "overlay_failure_count": _overlay_stats["failure_count"],
        "overlay_success_rate_pct": round(
            (_overlay_stats["success_count"] / total * 100) if total > 0 else 0.0, 1
        ),
        "last_success_at": _overlay_stats["last_success_at"],
        "last_failure_at": _overlay_stats["last_failure_at"],
        "last_failure_reason": _overlay_stats["last_failure_reason"],
        "last_model_used": _overlay_stats["last_model_used"],
        "last_latency_seconds": _overlay_stats["last_latency_seconds"],
        "avg_latency_seconds": _overlay_stats["avg_latency_seconds"],
    }


def _record_latency(seconds: float) -> None:
    samples = _overlay_stats["_latency_samples"]
    samples.append(seconds)
    if len(samples) > 100:
        _overlay_stats["_latency_samples"] = samples[-100:]
        samples = _overlay_stats["_latency_samples"]
    _overlay_stats["last_latency_seconds"] = round(seconds, 4)
    _overlay_stats["avg_latency_seconds"] = round(sum(samples) / len(samples), 4)


# ---------------------------------------------------------------------------
# Bias inference
# ---------------------------------------------------------------------------

def _bias_from_signal(signal: str) -> str:
    return "bullish" if signal == "BUY" else "bearish" if signal == "SELL" else "neutral"


# ---------------------------------------------------------------------------
# Structured prompt builder
# ---------------------------------------------------------------------------

def _build_overlay_prompt(
    package: DecisionPackage,
    market_ctx: dict,
    risk_ctx: dict,
    news_items: list[dict],
    strategy_ctx: dict,
) -> str:
    """Build a comprehensive structured prompt for the AI overlay.

    Feeds the LLM with deterministic facts and asks for a structured
    bias/explanation response. Never asks for execution recommendations.
    """
    signal_info = package.signal_layer
    price_info = package.price_layer
    risk_info = package.risk_layer

    sections: list[str] = []

    # Core signal context
    sections.append(
        f"Symbol: {package.symbol}\n"
        f"Signal: {signal_info.signal} (confidence: {signal_info.confidence:.0f}%)\n"
        f"Price: {price_info.price:.2f}"
        + (f", Support: {price_info.support:.2f}" if price_info.support else "")
        + (f", Resistance: {price_info.resistance:.2f}" if price_info.resistance else "")
        + (f"\nTrend: {price_info.trend}" if price_info.trend != "unknown" else "")
    )

    # Technical scores
    score_parts = []
    if signal_info.technical_score is not None:
        score_parts.append(f"Technical: {signal_info.technical_score:.1f}")
    if signal_info.mtf_score is not None:
        score_parts.append(f"MTF: {signal_info.mtf_score:.1f}")
    if signal_info.rs_score is not None:
        score_parts.append(f"RS: {signal_info.rs_score:.1f}")
    if signal_info.ensemble_signal:
        score_parts.append(f"Ensemble: {signal_info.ensemble_signal} ({signal_info.ensemble_confidence:.0f}%)" if signal_info.ensemble_confidence else f"Ensemble: {signal_info.ensemble_signal}")
    if score_parts:
        sections.append("Scores: " + ", ".join(score_parts))

    # Risk context
    risk_parts = []
    if risk_info.entry_price:
        risk_parts.append(f"Entry: {risk_info.entry_price:.2f}")
    if risk_info.stop_loss:
        risk_parts.append(f"Stop: {risk_info.stop_loss:.2f}")
    if risk_info.take_profit:
        risk_parts.append(f"Target: {risk_info.take_profit:.2f}")
    if risk_info.risk_reward_ratio:
        risk_parts.append(f"R/R: {risk_info.risk_reward_ratio:.2f}")
    if risk_parts:
        sections.append("Risk plan: " + ", ".join(risk_parts))

    # Portfolio risk from gateway
    if risk_ctx and not risk_ctx.get("error"):
        portfolio_parts = []
        if risk_ctx.get("gross_exposure_pct") is not None:
            portfolio_parts.append(f"Portfolio exposure: {risk_ctx['gross_exposure_pct']:.1f}%")
        if risk_ctx.get("max_drawdown_pct") is not None:
            portfolio_parts.append(f"Max drawdown: {risk_ctx['max_drawdown_pct']:.1f}%")
        if risk_ctx.get("current_state"):
            portfolio_parts.append(f"Risk state: {risk_ctx['current_state']}")
        if portfolio_parts:
            sections.append("Portfolio: " + ", ".join(portfolio_parts))

    # Live market context from gateway
    if market_ctx and not market_ctx.get("error"):
        live_price = market_ctx.get("price")
        if live_price is not None:
            sections.append(f"Live price: {live_price}")

    # News context from gateway
    if news_items:
        titles = [n.get("title", "")[:80] for n in news_items[:3] if n.get("title")]
        if titles:
            sections.append("Recent news:\n- " + "\n- ".join(titles))

    # Strategy context from gateway
    if strategy_ctx and not strategy_ctx.get("error") and strategy_ctx.get("items") != []:
        best = strategy_ctx.get("best_strategy") or strategy_ctx.get("strategy")
        if best:
            sections.append(f"Strategy context: Best strategy = {best}")

    # Existing deterministic factors
    if package.ai_layer.supporting_factors:
        sections.append("Supporting factors: " + "; ".join(package.ai_layer.supporting_factors[:4]))
    if package.ai_layer.caveats:
        sections.append("Caveats: " + "; ".join(package.ai_layer.caveats[:3]))
    if package.ai_layer.contradictions:
        sections.append("Contradictions: " + "; ".join(package.ai_layer.contradictions[:3]))

    # Instruction
    sections.append(
        "\n---\n"
        "You are a conservative financial analysis assistant. Based ONLY on the data above:\n"
        "1. State your bias: bullish, bearish, or neutral\n"
        "2. Rate confidence 0-100 (be conservative)\n"
        "3. Write a 1-2 sentence concise explanation of the bias\n"
        "4. List 1-2 key contradictions or caveats the trader should watch\n"
        "5. Summarize news relevance in one sentence (or 'No significant news')\n\n"
        "IMPORTANT: Do NOT give trading instructions, order placements, or execution advice.\n"
        "Respond ONLY in this JSON format:\n"
        '{"bias":"bullish|bearish|neutral","confidence":0-100,"explanation":"...","contradictions":["..."],"news_summary":"..."}'
    )

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_ai_response(raw_text: str, package: DecisionPackage) -> dict:
    """Parse AI response into structured fields with fallback."""
    # Try JSON parse first
    text = raw_text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    try:
        parsed = json.loads(text)
        bias = str(parsed.get("bias", "")).lower()
        if bias not in ("bullish", "bearish", "neutral"):
            bias = _bias_from_signal(package.signal_layer.signal)

        confidence = float(parsed.get("confidence", package.signal_layer.confidence))
        confidence = max(0.0, min(100.0, confidence))

        return {
            "bias": bias,
            "confidence": confidence,
            "explanation": str(parsed.get("explanation", ""))[:500] or None,
            "contradictions": [str(c)[:200] for c in (parsed.get("contradictions") or [])[:5]],
            "news_summary": str(parsed.get("news_summary", ""))[:300] or None,
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        # Fallback: use raw text as explanation
        return {
            "bias": _bias_from_signal(package.signal_layer.signal),
            "confidence": package.signal_layer.confidence,
            "explanation": text[:500] if text else None,
            "contradictions": [],
            "news_summary": None,
        }


# ---------------------------------------------------------------------------
# Main enrichment function
# ---------------------------------------------------------------------------

def enrich_with_ai_overlay(package: DecisionPackage) -> DecisionPackage:
    """Attempt to enrich the ``ai_layer`` with an LLM-generated overlay.

    Returns a new ``DecisionPackage`` with an updated ``ai_layer``.
    The original package is NOT mutated.

    The function uses the ToolGateway for all data acquisition (market, news,
    risk, strategy context). It falls back silently to the deterministic
    explanation if AI is unavailable. It never modifies price_layer,
    signal_layer, or risk_layer.

    Observability: records latency, success/failure counters, and model used.
    """
    _overlay_stats["total_calls"] += 1
    start_time = time.monotonic()
    gateway = get_tool_gateway()

    # ------------------------------------------------------------------
    # Gather context via the tool gateway (all AI-safe, non-executable)
    # ------------------------------------------------------------------
    market_ctx = gateway.call("get_market_context", symbol=package.symbol)
    news_result = gateway.call("get_news_context", symbol=package.symbol, limit=5)
    news_items = news_result.get("items", []) if not news_result.get("error") else []
    risk_ctx = gateway.call("get_risk_summary")
    strategy_ctx = gateway.call("get_strategy_metrics", symbol=package.symbol)

    # Build news summary from gateway data
    news_summary: str | None = package.ai_layer.news_summary
    if news_items and not news_summary:
        titles = [n.get("title", "") for n in news_items[:3] if n.get("title")]
        if titles:
            news_summary = " | ".join(titles[:2])

    try:
        from backend.app.services.llm_gateway import llm_chat, LLMUnavailableError  # noqa: PLC0415

        # Build comprehensive structured prompt
        prompt = _build_overlay_prompt(
            package=package,
            market_ctx=market_ctx,
            risk_ctx=risk_ctx,
            news_items=news_items,
            strategy_ctx=strategy_ctx,
        )

        # Try LLM gateway first (unified Ollama/OpenAI interface)
        llm_response = llm_chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a conservative financial analysis overlay. "
                        "You ONLY explain and summarize deterministic analysis results. "
                        "You NEVER suggest trades, order placements, or execution actions. "
                        "Respond in the exact JSON format requested."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.15,
        )
        raw_text = llm_response["content"].strip()
        model_used = llm_response.get("model", "unknown")
        provider_used = llm_response.get("provider", "unknown")

        # Parse structured response
        parsed = _parse_ai_response(raw_text, package)

        elapsed = time.monotonic() - start_time
        _record_latency(elapsed)

        ai_layer = AIBiasOverlay(
            bias=parsed["bias"],
            confidence=parsed["confidence"],
            explanation=parsed["explanation"],
            supporting_factors=package.ai_layer.supporting_factors,
            contradictions=parsed["contradictions"] or package.ai_layer.contradictions,
            caveats=package.ai_layer.caveats,
            news_summary=parsed["news_summary"] or news_summary,
            source=provider_used,
            model_used=model_used,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Record success
        _overlay_stats["success_count"] += 1
        _overlay_stats["last_success_at"] = datetime.now(timezone.utc).isoformat()
        _overlay_stats["last_model_used"] = model_used

        log_event(logger, logging.INFO, "ai_overlay.enriched",
                  symbol=package.symbol, source=provider_used, model=model_used,
                  latency_s=round(elapsed, 3))

        # Record observability metrics
        try:
            from backend.app.services.observability import (
                record_ai_overlay_latency,
                record_tool_call,
            )
            record_ai_overlay_latency(source=provider_used, latency_seconds=elapsed)
            record_tool_call(tool="ai_overlay", outcome="success")
        except Exception:
            pass

        return package.model_copy(update={
            "ai_layer": ai_layer,
            "deterministic_only": False,
        })

    except Exception as exc:
        elapsed = time.monotonic() - start_time
        _record_latency(elapsed)

        # Record failure/fallback
        _overlay_stats["fallback_count"] += 1
        _overlay_stats["last_failure_at"] = datetime.now(timezone.utc).isoformat()
        _overlay_stats["last_failure_reason"] = str(exc)[:200]

        log_event(logger, logging.WARNING, "ai_overlay.fallback",
                  symbol=package.symbol, reason=str(exc)[:100],
                  latency_s=round(elapsed, 3))

        # Record observability
        try:
            from backend.app.services.observability import (
                record_ai_overlay_latency,
                record_tool_call,
            )
            record_ai_overlay_latency(source="fallback", latency_seconds=elapsed)
            record_tool_call(tool="ai_overlay", outcome="fallback")
        except Exception:
            pass

        # Silent fallback — preserve the deterministic explanation
        ai_layer = AIBiasOverlay(
            bias=package.ai_layer.bias,
            confidence=package.ai_layer.confidence,
            explanation=package.ai_layer.explanation,
            supporting_factors=package.ai_layer.supporting_factors,
            contradictions=package.ai_layer.contradictions,
            caveats=package.ai_layer.caveats,
            news_summary=news_summary or package.ai_layer.news_summary,
            source="fallback",
            model_used=None,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        return package.model_copy(update={
            "ai_layer": ai_layer,
            "deterministic_only": True,
        })
