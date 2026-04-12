"""Smart Automation — AI-powered market monitoring and alert generation.

Runs periodically via the scheduler to:
1. Scan top-ranked symbols for signal changes
2. Use Ollama (local LLM) to generate contextual market insights
3. Produce smart alerts with AI explanations
4. Track opportunities and generate trade suggestions

This replaces the need for manual market checking — the system
proactively finds and explains opportunities.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)

# In-memory store for latest smart cycle results
_last_smart_cycle: dict | None = None
_smart_alerts: list[dict] = []
_MAX_ALERTS = 50


def get_smart_automation_status() -> dict:
    """Return current smart automation state for the API."""
    return {
        "last_cycle": _last_smart_cycle,
        "alerts_count": len(_smart_alerts),
        "recent_alerts": _smart_alerts[:10],
    }


def get_smart_alerts(limit: int = 20) -> list[dict]:
    """Return recent smart alerts."""
    return _smart_alerts[:limit]


def clear_smart_alerts() -> int:
    """Clear all smart alerts. Returns count cleared."""
    global _smart_alerts
    count = len(_smart_alerts)
    _smart_alerts = []
    return count


async def run_smart_cycle(
    symbols: list[str] | None = None,
    symbol_limit: int = 10,
) -> dict:
    """Run one smart automation cycle.

    Steps:
    1. Get top-ranked symbols (or use provided list)
    2. Run analysis on each
    3. Ask Ollama to explain opportunities
    4. Generate alerts for actionable signals
    """
    from backend.app.config import AUTOMATION_SYMBOL_LIMIT

    global _last_smart_cycle

    started = time.perf_counter()
    cycle_time = datetime.now(timezone.utc).isoformat()
    limit = min(symbol_limit or AUTOMATION_SYMBOL_LIMIT, 20)

    log_event(logger, logging.INFO, "smart_cycle.start", symbol_limit=limit)

    # Step 1: Get symbols to analyze
    target_symbols = symbols or _get_top_symbols(limit)
    if not target_symbols:
        result = {
            "status": "skipped",
            "reason": "No symbols to analyze",
            "timestamp": cycle_time,
        }
        _last_smart_cycle = result
        return result

    # Step 2: Run analysis on each symbol
    analyses = []
    for symbol in target_symbols[:limit]:
        try:
            analysis = _analyze_symbol(symbol)
            if analysis and not analysis.get("error"):
                analyses.append(analysis)
        except Exception as exc:
            logger.warning("Smart cycle: analysis failed for %s: %s", symbol, exc)

    if not analyses:
        result = {
            "status": "completed",
            "reason": "No valid analyses produced",
            "symbols_attempted": len(target_symbols),
            "timestamp": cycle_time,
        }
        _last_smart_cycle = result
        return result

    # Step 3: Identify opportunities (BUY/SELL with decent confidence)
    opportunities = []
    for a in analyses:
        signal = str(a.get("signal", "HOLD")).upper()
        quality = a.get("signal_quality", "LOW")
        confidence = a.get("signal_confidence", 0)

        if signal in ("BUY", "SELL") and confidence >= 45:
            opportunities.append({
                "symbol": a.get("symbol", "?"),
                "signal": signal,
                "score": a.get("score", 0),
                "confidence": confidence,
                "quality": quality,
                "price": a.get("current_price"),
                "recommendation": a.get("enhanced_recommendation", ""),
                "confirmations": a.get("confirmation_factors", []),
                "warnings": a.get("warning_factors", []),
            })

    # Sort by confidence descending
    opportunities.sort(key=lambda x: x["confidence"], reverse=True)

    # Step 4: Generate AI summary with Ollama
    ai_summary = None
    if opportunities:
        ai_summary = _generate_ai_summary(opportunities)

    # Step 5: Create alerts
    new_alerts = []
    for opp in opportunities[:5]:  # Top 5 only
        alert = {
            "id": f"smart_{int(time.time())}_{opp['symbol']}",
            "type": "smart_opportunity",
            "symbol": opp["symbol"],
            "signal": opp["signal"],
            "confidence": opp["confidence"],
            "quality": opp["quality"],
            "price": opp["price"],
            "recommendation": opp["recommendation"],
            "confirmations": opp["confirmations"],
            "warnings": opp["warnings"],
            "timestamp": cycle_time,
            "ai_summary": ai_summary.get(opp["symbol"]) if isinstance(ai_summary, dict) else None,
        }
        new_alerts.append(alert)
        _smart_alerts.insert(0, alert)

    # Trim alerts history
    if len(_smart_alerts) > _MAX_ALERTS:
        _smart_alerts[:] = _smart_alerts[:_MAX_ALERTS]

    elapsed = round(time.perf_counter() - started, 2)

    result = {
        "status": "completed",
        "timestamp": cycle_time,
        "elapsed_seconds": elapsed,
        "symbols_analyzed": len(analyses),
        "opportunities_found": len(opportunities),
        "alerts_generated": len(new_alerts),
        "top_opportunities": opportunities[:5],
        "ai_summary": ai_summary if isinstance(ai_summary, str) else None,
    }

    _last_smart_cycle = result
    log_event(logger, logging.INFO, "smart_cycle.done",
              analyzed=len(analyses), opportunities=len(opportunities), elapsed_s=elapsed)

    return result


def _get_top_symbols(limit: int) -> list[str]:
    """Get symbols from the market universe or watchlist."""
    try:
        from backend.app.services.market_universe import get_default_universe_symbols
        symbols = get_default_universe_symbols()
        return symbols[:limit] if symbols else []
    except Exception:
        pass

    # Fallback: try sample symbols from config
    try:
        from backend.app.config import MARKET_AI_SAMPLE_SYMBOLS
        if hasattr(MARKET_AI_SAMPLE_SYMBOLS, 'split'):
            return [s.strip() for s in MARKET_AI_SAMPLE_SYMBOLS.split(",") if s.strip()][:limit]
    except Exception:
        pass

    # Last resort
    return ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "META", "SPY"][:limit]


def _analyze_symbol(symbol: str) -> dict | None:
    """Run analysis on a single symbol using the analysis engine."""
    try:
        from core.analysis_service import run_analysis
        return run_analysis(symbol)
    except Exception:
        pass

    try:
        from analysis_engine import analyze_stock
        return analyze_stock(symbol)
    except Exception as exc:
        logger.debug("Analysis failed for %s: %s", symbol, exc)
        return None


def _generate_ai_summary(opportunities: list[dict]) -> str | dict | None:
    """Use Ollama to generate a market summary of opportunities."""
    try:
        from backend.app.services.llm_gateway import llm_chat, LLMUnavailableError
    except ImportError:
        return None

    if not opportunities:
        return None

    # Build a concise prompt
    opp_lines = []
    for o in opportunities[:8]:
        opp_lines.append(
            f"- {o['symbol']}: {o['signal']} (confidence {o['confidence']}%, "
            f"quality {o['quality']}, price ${o.get('price', '?')})"
        )

    prompt = f"""You are a concise market analyst. Analyze these trading opportunities and provide a brief summary (3-5 sentences) highlighting:
1. The strongest opportunity and why
2. Any common patterns across signals
3. Key risks to watch

Opportunities:
{chr(10).join(opp_lines)}

Be concise and actionable."""

    try:
        result = llm_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )
        return result.get("content", "")
    except Exception as exc:
        logger.debug("AI summary generation failed: %s", exc)
        return None
