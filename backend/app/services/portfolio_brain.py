from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from backend.app.models.market_data import MarketUniverseSymbol
from backend.app.services.market_data import fetch_quote_snapshots, load_history
from backend.app.services.storage import session_scope
from backend.app.services.trade_journal import list_trade_journal_entries


_INDEX_SYMBOLS = ("SPY", "QQQ", "IWM")
_EXECUTION_ACTIONS = {"OPEN_LONG", "ADD_LONG", "REDUCE_LONG", "EXIT_LONG"}
_CAPITAL_RELEASE_ACTIONS = {"EXIT_LONG", "REDUCE_LONG"}
_CAPITAL_DEPLOY_ACTIONS = {"OPEN_LONG", "ADD_LONG"}

_QUEUE_PRIORITY_RANK = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
    "deferred": 4,
}

_QUEUE_STAGE_RANK = {
    "capital_release": 0,
    "risk_action": 1,
    "deploy_full": 2,
    "deploy_partial": 3,
    "observe": 4,
}

_SESSION_QUALITY_RANK = {
    "excellent": 3,
    "good": 2,
    "normal": 1,
    "poor": 0,
    "closed": -1,
}

_SLEEVE_NAMES = (
    "tactical_aggressive",
    "swing_growth",
    "long_quality",
    "defensive_stability",
    "dividend_income",
    "cash",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(float(value), high))


def _safe_mean(values: list[float], default: float = 0.0) -> float:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return float(default)
    return float(sum(cleaned) / len(cleaned))


def _normalize_signal(value: Any) -> str:
    normalized = str(value or "HOLD").strip().upper()
    return normalized if normalized in {"BUY", "SELL", "HOLD"} else "HOLD"


def _priority_rank(value: Any) -> int:
    normalized = str(value or "deferred").strip().lower()
    return _QUEUE_PRIORITY_RANK.get(normalized, _QUEUE_PRIORITY_RANK["deferred"])


def _normalize_session_quality(value: Any) -> str:
    normalized = str(value or "normal").strip().lower()
    return normalized if normalized in _SESSION_QUALITY_RANK else "normal"


def _session_rank(value: Any) -> int:
    return _SESSION_QUALITY_RANK.get(_normalize_session_quality(value), 1)


def _iso_offset(base_iso: str | None, offset_seconds: float | int | None) -> str | None:
    base = str(base_iso or "").strip()
    if not base:
        return None
    try:
        dt = datetime.fromisoformat(base)
    except Exception:
        return None
    try:
        seconds = float(offset_seconds or 0.0)
    except Exception:
        seconds = 0.0
    if abs(seconds) <= 1e-9:
        return dt.isoformat()
    return (dt + timedelta(seconds=seconds)).isoformat()


def _derive_execution_stage(row: dict) -> str:
    action = str(row.get("requested_execution_action") or row.get("action_decision") or "HOLD").strip().upper()
    if action in _CAPITAL_RELEASE_ACTIONS:
        return "capital_release"
    if action in _CAPITAL_DEPLOY_ACTIONS:
        status = str(row.get("funding_status") or "").strip().lower()
        return "deploy_partial" if status == "partially_funded" else "deploy_full"
    return "observe"


def _extract_ensemble(result: dict | None) -> dict:
    if not isinstance(result, dict):
        return {}
    payload = result.get("ensemble_output")
    return payload if isinstance(payload, dict) else {}


def _price_from_candidate(candidate: dict) -> float:
    direct_price = _safe_float(candidate.get("price"), 0.0)
    if direct_price > 0:
        return direct_price
    result = candidate.get("result")
    if isinstance(result, dict):
        close_price = _safe_float(result.get("close"), 0.0)
        if close_price > 0:
            return close_price
        ml_payload = result.get("ml_output") if isinstance(result.get("ml_output"), dict) else {}
        ml_price = _safe_float(ml_payload.get("close"), 0.0)
        if ml_price > 0:
            return ml_price
    return 0.0


def _normalize_sentiment(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"BULLISH", "POSITIVE", "BUY", "UP"}:
        return "positive"
    if normalized in {"BEARISH", "NEGATIVE", "SELL", "DOWN"}:
        return "negative"
    if normalized in {"MIXED"}:
        return "mixed"
    return "neutral"


def _market_cap_bucket(value: float) -> str:
    market_cap = max(_safe_float(value, 0.0), 0.0)
    if market_cap <= 0.0:
        return "unknown"
    if market_cap < 300_000_000:
        return "micro"
    if market_cap < 2_000_000_000:
        return "small"
    if market_cap < 10_000_000_000:
        return "mid"
    if market_cap < 200_000_000_000:
        return "large"
    return "mega"


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    base = {name: max(_safe_float(weights.get(name), 0.0), 0.0) for name in _SLEEVE_NAMES}
    total = sum(base.values())
    if total <= 0.0:
        equal_weight = round(100.0 / max(len(_SLEEVE_NAMES), 1), 2)
        return {name: equal_weight for name in _SLEEVE_NAMES}
    normalized = {name: round((value / total) * 100.0, 2) for name, value in base.items()}
    drift = round(100.0 - sum(normalized.values()), 2)
    if abs(drift) > 1e-9:
        normalized["cash"] = round(normalized.get("cash", 0.0) + drift, 2)
    return normalized


def _load_symbol_universe_metadata(symbols: list[str]) -> dict[str, dict]:
    normalized_symbols = sorted({
        str(symbol or "").strip().upper()
        for symbol in (symbols or [])
        if str(symbol or "").strip()
    })
    if not normalized_symbols:
        return {}

    with session_scope() as session:
        rows = (
            session.query(MarketUniverseSymbol)
            .filter(MarketUniverseSymbol.symbol.in_(normalized_symbols))
            .all()
        )

    payload: dict[str, dict] = {}
    for row in rows:
        symbol = str(row.symbol or "").strip().upper()
        exchange = str(row.exchange or "").strip()
        market_type = str(row.market_type or "").strip()
        country = str(row.country or "").strip()
        market_cap = max(_safe_float(row.market_cap, 0.0), 0.0)
        exchange_upper = exchange.upper()
        market_type_upper = market_type.upper()
        country_upper = country.upper()
        us_equity = (
            not bool(row.is_etf)
            and ("US" in country_upper or "UNITED STATES" in country_upper or not country_upper)
            and "OTC" not in exchange_upper
            and "OTC" not in market_type_upper
        )
        bucket = _market_cap_bucket(market_cap)
        payload[symbol] = {
            "security_name": row.security_name,
            "exchange": exchange or None,
            "country": country or None,
            "market_type": market_type or None,
            "market_cap": round(market_cap, 4),
            "market_cap_bucket": bucket,
            "is_etf": bool(row.is_etf),
            "us_equity_eligible": bool(us_equity),
            "listed_exchange_ok": "OTC" not in exchange_upper and "OTC" not in market_type_upper,
            "tactical_small_cap_candidate": bucket == "small",
            "micro_cap_flag": bucket == "micro",
        }
    return payload


def _load_trend_metrics(symbol: str) -> dict:
    try:
        history = load_history(symbol, interval="1d", persist=False)
    except Exception as exc:
        return {
            "symbol": symbol,
            "trend_score": 0.0,
            "close": 0.0,
            "ma20": 0.0,
            "ma50": 0.0,
            "realized_volatility": 0.0,
            "error": str(exc),
        }

    items = history.get("items") if isinstance(history, dict) else []
    closes = [
        _safe_float(item.get("close"), 0.0)
        for item in (items or [])
        if _safe_float(item.get("close"), 0.0) > 0
    ]
    if len(closes) < 55:
        last_close = closes[-1] if closes else 0.0
        return {
            "symbol": symbol,
            "trend_score": 0.0,
            "close": round(last_close, 4),
            "ma20": round(last_close, 4),
            "ma50": round(last_close, 4),
            "realized_volatility": 0.0,
            "insufficient_history": True,
        }

    ma20 = mean(closes[-20:])
    ma50 = mean(closes[-50:])
    last_close = closes[-1]
    trend_score = 0.0
    if last_close > ma20:
        trend_score += 1.0
    elif last_close < ma20:
        trend_score -= 1.0
    if ma20 > ma50:
        trend_score += 1.0
    elif ma20 < ma50:
        trend_score -= 1.0

    trailing = closes[-20:]
    trailing_mean = max(mean(trailing), 1e-9)
    realized_vol = mean([abs((trailing[idx] - trailing[idx - 1]) / trailing[idx - 1]) for idx in range(1, len(trailing)) if trailing[idx - 1] > 0])

    return {
        "symbol": symbol,
        "trend_score": round(trend_score, 4),
        "close": round(last_close, 4),
        "ma20": round(ma20, 4),
        "ma50": round(ma50, 4),
        "realized_volatility": round(realized_vol * 100.0, 4),
        "normalized_trend_gap": round(((last_close / trailing_mean) - 1.0) * 100.0, 4),
    }


def build_market_judgment(
    *,
    regime: dict,
    session_snapshot: dict | None = None,
    portfolio_summary: dict | None = None,
) -> dict:
    session = session_snapshot if isinstance(session_snapshot, dict) else {}
    summary = portfolio_summary if isinstance(portfolio_summary, dict) else {}

    session_state = str(session.get("session_state") or "fully_closed").strip().lower() or "fully_closed"
    session_quality = _normalize_session_quality(session.get("session_quality"))
    readiness_phase = str(session.get("readiness_phase") or "standby").strip().lower() or "standby"
    regime_bias = str(regime.get("regime_bias") or "neutral").strip().lower() or "neutral"
    risk_multiplier = _clamp(_safe_float(regime.get("risk_multiplier"), 1.0), 0.1, 2.0)
    regime_confidence = _clamp(_safe_float(regime.get("regime_confidence"), 50.0), 0.0, 100.0)
    quality_seed = 52.0 + (risk_multiplier - 1.0) * 22.0 + regime_confidence * 0.08
    quality_seed += _session_rank(session_quality) * 6.0
    if regime_bias == "bullish":
        quality_seed += 8.0
    elif regime_bias == "defensive":
        quality_seed -= 8.0
    elif regime_bias == "risk_off":
        quality_seed -= 16.0
    if not bool(session.get("is_trading_day", True)):
        quality_seed -= 10.0
    if session_state == "opening_handoff_window":
        quality_seed += 4.0
    if session_state in {"after_hours", "fully_closed"}:
        quality_seed -= 4.0
    market_quality_score = round(_clamp(quality_seed, 0.0, 100.0), 4)

    market_offense_level = round(
        _clamp(
            50.0
            + (market_quality_score - 50.0) * 0.9
            + (8.0 if regime_bias == "bullish" else -10.0 if regime_bias in {"defensive", "risk_off"} else 0.0),
            0.0,
            100.0,
        ),
        4,
    )
    market_defense_level = round(
        _clamp(
            48.0
            + (15.0 if regime_bias == "risk_off" else 8.0 if regime_bias == "defensive" else -6.0 if regime_bias == "bullish" else 0.0)
            + max(0.0, 58.0 - market_quality_score) * 0.7,
            0.0,
            100.0,
        ),
        4,
    )
    market_cash_preference = round(
        _clamp(
            42.0
            + max(0.0, market_defense_level - market_offense_level) * 0.6
            + (6.0 if session_state in {"fully_closed", "after_hours"} else 0.0),
            0.0,
            100.0,
        ),
        4,
    )

    warning_flags: list[str] = []
    if not bool(session.get("is_trading_day", True)):
        warning_flags.append("non_trading_day")
    if bool(session.get("is_early_close", False)):
        warning_flags.append("early_close")
    if regime_bias in {"defensive", "risk_off"}:
        warning_flags.append("defensive_regime")
    if session_state in {"after_hours", "fully_closed"}:
        warning_flags.append("inactive_session")
    if session_quality == "poor":
        warning_flags.append("poor_session_quality")

    tactical_small_caps_allowed = bool(
        market_quality_score >= 58.0
        and market_offense_level >= market_defense_level
        and regime_bias not in {"defensive", "risk_off"}
        and session_state not in {"after_hours"}
    )
    premarket_participation_allowed = bool(
        bool(session.get("extended_hours_available", False))
        and session_state in {"preopen_preparation", "premarket_live", "opening_handoff_window"}
        and market_quality_score >= 52.0
        and regime_bias not in {"risk_off"}
    )
    open_handoff_readiness = bool(
        session_state in {"opening_handoff_window", "regular_session"}
        or readiness_phase == "open_handoff"
        or (bool(session.get("is_trading_day", False)) and 0 <= _safe_int(session.get("minutes_to_open"), 9999) <= 5)
    )

    return {
        "session_state": session_state,
        "market_open": bool(session.get("market_open", False)),
        "is_trading_day": bool(session.get("is_trading_day", False)),
        "is_early_close": bool(session.get("is_early_close", False)),
        "next_open_at": session.get("next_open_at"),
        "next_close_at": session.get("next_close_at"),
        "minutes_to_open": session.get("minutes_to_open"),
        "minutes_to_close": session.get("minutes_to_close"),
        "regime_code": regime.get("regime_code"),
        "regime_bias": regime_bias,
        "regime_confidence": regime.get("regime_confidence"),
        "risk_multiplier": regime.get("risk_multiplier"),
        "market_quality_score": market_quality_score,
        "market_warning_flags": warning_flags,
        "market_offense_level": market_offense_level,
        "market_defense_level": market_defense_level,
        "market_cash_preference": market_cash_preference,
        "tactical_small_caps_allowed": tactical_small_caps_allowed,
        "premarket_participation_allowed": premarket_participation_allowed,
        "open_handoff_readiness": open_handoff_readiness,
        "session_quality": session_quality,
        "session_notes": session.get("session_notes") if isinstance(session.get("session_notes"), list) else [],
        "readiness_phase": readiness_phase,
        "portfolio_equity": round(_safe_float(summary.get("total_equity") or summary.get("portfolio_value"), 0.0), 4),
    }


def _build_news_judgment(*, result: dict, signal: str, price_quality_score: float) -> dict:
    news_items = result.get("news_items") if isinstance(result.get("news_items"), list) else []
    sentiments = [_normalize_sentiment(item.get("sentiment")) for item in news_items]
    relevance_values = [_clamp(_safe_float(item.get("relevance_score"), 0.0) * 100.0, 0.0, 100.0) for item in news_items]
    impact_values = [_clamp(_safe_float(item.get("impact_score"), 0.0) * 100.0, 0.0, 100.0) for item in news_items]
    event_types = [str(item.get("event_type") or "general").strip().lower() or "general" for item in news_items]
    freshness = [str(item.get("event_relation") or "").strip().lower() for item in news_items]

    sentiment_counts = Counter(sentiments)
    event_counts = Counter(event_types)
    dominant_sentiment = "neutral"
    if sentiment_counts.get("positive", 0) > sentiment_counts.get("negative", 0):
        dominant_sentiment = "positive"
    elif sentiment_counts.get("negative", 0) > sentiment_counts.get("positive", 0):
        dominant_sentiment = "negative"
    elif sentiment_counts.get("mixed", 0) > 0:
        dominant_sentiment = "mixed"

    ai_sentiment = _normalize_sentiment(result.get("ai_news_sentiment") or result.get("news_sentiment"))
    if dominant_sentiment == "neutral" and ai_sentiment != "neutral":
        dominant_sentiment = ai_sentiment

    positive_count = sentiment_counts.get("positive", 0)
    negative_count = sentiment_counts.get("negative", 0)
    neutral_count = sentiment_counts.get("neutral", 0) + sentiment_counts.get("mixed", 0)
    total_news = len(news_items)

    raw_sentiment = ((positive_count - negative_count) / max(total_news, 1)) * 100.0
    ai_news_score = _safe_float(result.get("ai_news_score"), 0.0) * 8.0
    news_score_raw = _safe_float(result.get("news_score"), 0.0) * 6.0
    news_sentiment_score = round(_clamp(raw_sentiment + ai_news_score + news_score_raw, -100.0, 100.0), 4)

    relevance_score = round(_clamp(_safe_mean(relevance_values, 0.0), 0.0, 100.0), 4)
    strength_score = round(
        _clamp(_safe_mean(impact_values, 0.0) * 0.72 + min(total_news, 6) * 6.0 + abs(news_sentiment_score) * 0.12, 0.0, 100.0),
        4,
    )
    news_confidence = round(
        _clamp(relevance_score * 0.42 + strength_score * 0.38 + min(total_news, 5) * 4.0 + price_quality_score * 0.12, 0.0, 100.0),
        4,
    )

    catalyst_type = event_counts.most_common(1)[0][0] if event_counts else "general"
    if catalyst_type in {"macro", "fed", "rates", "cpi"}:
        catalyst_scope = "market"
    elif catalyst_type in {"sector", "industry"}:
        catalyst_scope = "sector"
    else:
        catalyst_scope = "symbol"

    if any(item in {"fresh", "breaking"} for item in freshness):
        catalyst_horizon = "intraday"
    elif total_news >= 3:
        catalyst_horizon = "multi_day"
    else:
        catalyst_horizon = "swing"

    alignment = "mixed"
    if signal == "BUY":
        alignment = "supportive" if news_sentiment_score >= 12 else "contrarian" if news_sentiment_score <= -12 else "mixed"
    elif signal == "SELL":
        alignment = "supportive" if news_sentiment_score <= -12 else "contrarian" if news_sentiment_score >= 12 else "mixed"

    warning_flags: list[str] = []
    if total_news == 0:
        warning_flags.append("no_recent_news")
    if dominant_sentiment == "mixed":
        warning_flags.append("mixed_news_flow")
    if alignment == "contrarian":
        warning_flags.append("news_price_conflict")
    if strength_score >= 70.0 and relevance_score < 55.0:
        warning_flags.append("high_noise_headline_risk")

    news_supports_entry = dominant_sentiment == "positive" and alignment == "supportive" and strength_score >= 52.0
    news_supports_add = news_supports_entry and news_confidence >= 60.0
    news_supports_reduce = dominant_sentiment == "negative" and strength_score >= 42.0
    news_supports_exit = dominant_sentiment == "negative" and strength_score >= 68.0
    news_requires_wait = bool(
        dominant_sentiment == "mixed"
        or (alignment == "contrarian" and abs(news_sentiment_score) >= 18.0)
        or (strength_score >= 72.0 and relevance_score < 60.0)
    )

    if news_supports_exit:
        action_bias = "EXIT_LONG"
    elif news_supports_reduce:
        action_bias = "REDUCE_LONG"
    elif news_requires_wait:
        action_bias = "WAIT"
    elif news_supports_entry:
        action_bias = "OPEN_LONG"
    else:
        action_bias = "NO_ACTION"

    no_trade_reason = None
    if total_news == 0:
        no_trade_reason = "no_recent_news_confirmation"
    elif news_requires_wait:
        no_trade_reason = "mixed_or_unconfirmed_catalyst"
    elif dominant_sentiment == "negative" and signal == "BUY":
        no_trade_reason = "negative_catalyst_conflicts_with_long_bias"

    contribution = round(_clamp((news_sentiment_score / 20.0) + (strength_score - 50.0) * 0.03 + (relevance_score - 50.0) * 0.02, -8.0, 8.0), 4)

    return {
        "news_relevance_score": relevance_score,
        "news_sentiment_score": news_sentiment_score,
        "news_strength_score": strength_score,
        "catalyst_type": catalyst_type,
        "catalyst_horizon": catalyst_horizon,
        "catalyst_scope": catalyst_scope,
        "catalyst_alignment_with_price": alignment,
        "news_confidence": news_confidence,
        "news_warning_flags": warning_flags,
        "news_action_bias": action_bias,
        "news_supports_entry": news_supports_entry,
        "news_supports_add": news_supports_add,
        "news_supports_reduce": news_supports_reduce,
        "news_supports_exit": news_supports_exit,
        "news_requires_wait": news_requires_wait,
        "news_no_trade_reason": no_trade_reason,
        "news_contribution_to_score": contribution,
    }


def build_market_regime(
    *,
    candidate_rows: list[dict],
    market_open: bool,
    auto_trading_config: dict | None = None,
) -> dict:
    config = auto_trading_config if isinstance(auto_trading_config, dict) else {}
    index_snapshot = fetch_quote_snapshots(list(_INDEX_SYMBOLS), include_profile=False)
    index_map = {
        str(item.get("symbol") or "").upper(): item
        for item in (index_snapshot.get("items") or [])
        if item.get("symbol")
    }
    index_metrics = [_load_trend_metrics(symbol) for symbol in _INDEX_SYMBOLS]

    trend_score_total = sum(_safe_float(item.get("trend_score"), 0.0) for item in index_metrics)
    trend_score_avg = trend_score_total / max(len(index_metrics), 1)
    change_pcts = [
        _safe_float(index_map.get(symbol, {}).get("change_pct"), 0.0)
        for symbol in _INDEX_SYMBOLS
    ]
    realized_volatility = mean([
        _safe_float(item.get("realized_volatility"), 0.0)
        for item in index_metrics
    ]) if index_metrics else 0.0

    buy_candidates = 0
    sell_candidates = 0
    for row in (candidate_rows or []):
        signal = _normalize_signal(row.get("signal") or row.get("analysis_signal"))
        if signal == "BUY":
            buy_candidates += 1
        elif signal == "SELL":
            sell_candidates += 1
    participation = (buy_candidates - sell_candidates) / max((buy_candidates + sell_candidates), 1)

    stress = bool(
        min(change_pcts or [0.0]) <= -2.0
        or max(change_pcts or [0.0]) >= 2.4
        or realized_volatility >= 2.4
    )

    regime_code = "normal"
    regime_bias = "neutral"
    regime_confidence = 58.0
    risk_multiplier = 1.0
    max_gross_exposure_pct = 72.0
    max_new_positions = max(1, min(_safe_int(config.get("portfolio_max_new_positions"), 2), 12))
    add_allowed = True
    reduce_bias = False

    if not market_open:
        regime_code = "mostly_inactive"
        regime_bias = "risk_off"
        regime_confidence = 88.0
        risk_multiplier = 0.35
        max_gross_exposure_pct = 30.0
        max_new_positions = 0
        add_allowed = False
        reduce_bias = True
    elif trend_score_avg <= -0.55 or participation <= -0.22 or stress:
        regime_code = "defensive" if trend_score_avg > -1.05 else "risk_off"
        regime_bias = "defensive" if regime_code == "defensive" else "risk_off"
        regime_confidence = 74.0 if regime_code == "defensive" else 84.0
        risk_multiplier = 0.55 if regime_code == "defensive" else 0.4
        max_gross_exposure_pct = 45.0 if regime_code == "defensive" else 35.0
        max_new_positions = min(max_new_positions, 1 if regime_code == "defensive" else 0)
        add_allowed = regime_code == "defensive"
        reduce_bias = True
    elif trend_score_avg >= 0.85 and participation >= 0.2 and not stress:
        regime_code = "aggressive"
        regime_bias = "bullish"
        regime_confidence = 76.0
        risk_multiplier = 1.2
        max_gross_exposure_pct = 92.0
        max_new_positions = max(max_new_positions, 3)
        add_allowed = True
        reduce_bias = False

    if not bool(config.get("regime_enabled", True)):
        regime_code = "regime_disabled"
        regime_bias = "neutral"
        regime_confidence = 50.0
        risk_multiplier = 1.0
        max_gross_exposure_pct = 72.0
        reduce_bias = False

    max_gross_cap = _safe_float(config.get("portfolio_max_gross_exposure_pct"), max_gross_exposure_pct)
    if max_gross_cap > 0:
        max_gross_exposure_pct = min(max_gross_exposure_pct, max_gross_cap)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "regime_code": regime_code,
        "regime_bias": regime_bias,
        "regime_confidence": round(_clamp(regime_confidence, 0.0, 100.0), 2),
        "risk_multiplier": round(_clamp(risk_multiplier, 0.1, 2.0), 4),
        "max_gross_exposure_pct": round(_clamp(max_gross_exposure_pct, 0.0, 100.0), 2),
        "max_new_positions": max(0, int(max_new_positions)),
        "add_allowed": bool(add_allowed),
        "reduce_bias": bool(reduce_bias),
        "session_open": bool(market_open),
        "notes": [
            f"trend_score_avg={trend_score_avg:.3f}",
            f"participation={participation:.3f}",
            f"realized_volatility={realized_volatility:.3f}",
        ],
        "components": {
            "index_changes": {
                symbol: round(_safe_float(index_map.get(symbol, {}).get("change_pct"), 0.0), 4)
                for symbol in _INDEX_SYMBOLS
            },
            "index_trends": index_metrics,
            "candidate_buy_count": int(buy_candidates),
            "candidate_sell_count": int(sell_candidates),
            "candidate_participation": round(participation, 4),
            "stress": bool(stress),
        },
    }


def _conviction_tier(score: float) -> str:
    if score >= 82:
        return "elite"
    if score >= 70:
        return "high"
    if score >= 58:
        return "medium"
    if score >= 46:
        return "watch"
    return "low"


def _risk_reward_estimate(score: float, signal: str) -> float:
    direction_factor = 1.0 if signal == "BUY" else 0.7 if signal == "SELL" else 0.4
    return round(_clamp((score / 100.0) * 2.8 * direction_factor, 0.1, 3.2), 2)


def build_opportunity_rows(
    *,
    candidate_rows: list[dict],
    strategy_mode: str,
    regime: dict,
    market_judgment: dict | None = None,
) -> list[dict]:
    regime_bias = str(regime.get("regime_bias") or "neutral").strip().lower()
    judgment = market_judgment if isinstance(market_judgment, dict) else {}
    symbol_profiles = _load_symbol_universe_metadata([
        str(row.get("symbol") or "").strip().upper()
        for row in (candidate_rows or [])
        if str(row.get("symbol") or "").strip()
    ])
    opportunities: list[dict] = []

    def _metric_score(value: Any, *, small_scale: float = 20.0) -> float:
        raw = abs(_safe_float(value, 0.0))
        if raw <= 5.0:
            raw *= small_scale
        elif raw <= 10.0:
            raw *= 10.0
        return _clamp(raw, 0.0, 100.0)

    def _categorical_risk(value: float) -> str:
        if value >= 70:
            return "high"
        if value >= 42:
            return "medium"
        return "low"

    def _small_cap_multiplier(profile: dict, *, score: float, liquidity: float, spread_risk_value: float) -> tuple[float, float, bool, str | None]:
        bucket = str(profile.get("market_cap_bucket") or "unknown").strip().lower()
        if bucket != "small":
            return 1.0, 0.0, False, None
        if not bool(judgment.get("tactical_small_caps_allowed", False)):
            return 0.55, 42.0, False, "market_quality_blocks_small_caps"
        if bool(profile.get("micro_cap_flag")):
            return 0.35, 28.0, False, "micro_cap_excluded"
        if liquidity < 48.0:
            return 0.55, 46.0, False, "small_cap_liquidity_too_low"
        if spread_risk_value >= 60.0:
            return 0.55, 44.0, False, "small_cap_spread_too_wide"
        multiplier = _clamp(0.48 + score / 180.0 + liquidity / 220.0, 0.35, 0.9)
        tactical_score = _clamp(score * 0.35 + liquidity * 0.22 + max(0.0, 100.0 - spread_risk_value) * 0.18, 0.0, 100.0)
        return multiplier, tactical_score, True, None

    for row in candidate_rows or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        profile = symbol_profiles.get(symbol, {})
        ensemble = _extract_ensemble(result)
        components = ensemble.get("components") if isinstance(ensemble.get("components"), dict) else {}
        ml_output = result.get("ml_output") if isinstance(result.get("ml_output"), dict) else {}
        dl_output = result.get("dl_output") if isinstance(result.get("dl_output"), dict) else {}

        signal = _normalize_signal(row.get("signal") or row.get("analysis_signal") or result.get("signal"))
        ranking_signal = _normalize_signal(result.get("smart_signal") or result.get("enhanced_signal") or result.get("signal") or signal)
        ml_signal = _normalize_signal(ml_output.get("signal") or ml_output.get("prediction") or ml_output.get("predicted_signal"))
        dl_signal = _normalize_signal(dl_output.get("signal") or result.get("dl_signal"))
        confidence = _safe_float(row.get("confidence"), 0.0)
        agreement_ratio = _safe_float(ensemble.get("agreement_ratio"), 0.0)

        technical_score = _metric_score(result.get("technical_score"), small_scale=10.0)
        ranking_score = _metric_score(result.get("rank_score") or result.get("enhanced_combined_score"), small_scale=10.0)
        mtf_score = _metric_score(result.get("mtf_score"), small_scale=20.0)
        trend_quality_score = _metric_score(result.get("trend_quality_score"), small_scale=10.0)
        relative_strength_score = _metric_score(result.get("rs_score") or result.get("rs_benchmark") or result.get("rs_spy_20"), small_scale=12.5)
        sector_strength_score = _metric_score(result.get("sector_strength_score") or (relative_strength_score * 0.88), small_scale=1.0)
        news_score = _metric_score(result.get("news_score"), small_scale=10.0)
        volume_ratio = max(_safe_float(result.get("volume_ratio"), 1.0), 0.0)
        volatility20 = max(_safe_float(result.get("volatility20"), 0.0), 0.0)
        atr14 = max(_safe_float(result.get("atr14"), 0.0), 0.0)
        gap_pct = _safe_float(result.get("gap_pct"), 0.0)
        risk_reward_estimate = _safe_float(result.get("risk_reward"), 0.0)
        price = _price_from_candidate(row)

        gap_type = "gap_up" if gap_pct >= 0.45 else "gap_down" if gap_pct <= -0.45 else "flat"
        gap_quality_score = _clamp(48.0 + min(abs(gap_pct), 4.5) * 8.0 + (trend_quality_score - 50.0) * 0.22 - volatility20 * 2.1, 0.0, 100.0)
        liquidity_score = _clamp(28.0 + min(volume_ratio, 4.0) * 17.0 + min(max(price, 0.0), 120.0) * 0.18, 0.0, 100.0)
        volatility_risk_value = _clamp(volatility20 * 18.0 + max(abs(gap_pct) - 1.0, 0.0) * 10.0 + atr14 * 0.6, 0.0, 100.0)
        spread_risk_value = _clamp(72.0 - liquidity_score + max(0.0, 15.0 - min(price, 15.0)) * 1.5, 0.0, 100.0)
        stock_quality_score = _clamp(
            technical_score * 0.18
            + ranking_score * 0.12
            + mtf_score * 0.13
            + trend_quality_score * 0.14
            + relative_strength_score * 0.14
            + sector_strength_score * 0.08
            + liquidity_score * 0.11
            + max(0.0, 100.0 - volatility_risk_value) * 0.10,
            0.0,
            100.0,
        )

        component_signals = {
            "classic": signal,
            "ranking": ranking_signal,
            "ml": ml_signal,
            "dl": dl_signal,
        }
        directional_signals = [value for value in component_signals.values() if value in {"BUY", "SELL"}]
        directional_counter = Counter(directional_signals)
        engine_conflicts_present = len(directional_counter) > 1
        engine_alignment_score = round((max(directional_counter.values()) / max(len(directional_signals), 1)) * 100.0, 4) if directional_signals else 0.0
        engine_conflict_reason = "buy_sell_engine_split" if engine_conflicts_present else None

        classic_component = round(_safe_float(components.get("classic_component"), technical_score / 100.0), 4)
        ranking_component = round(_safe_float(result.get("rank_score"), ranking_score) / 100.0, 4)

        opening_score = _clamp(
            technical_score * 0.18
            + ranking_score * 0.14
            + relative_strength_score * 0.16
            + trend_quality_score * 0.14
            + gap_quality_score * 0.16
            + liquidity_score * 0.12
            + (confidence * 0.10),
            0.0,
            100.0,
        )
        premarket_score = _clamp(
            gap_quality_score * 0.24
            + relative_strength_score * 0.18
            + liquidity_score * 0.22
            + trend_quality_score * 0.12
            + news_score * 0.12
            + max(0.0, 100.0 - volatility_risk_value) * 0.12,
            0.0,
            100.0,
        )
        breakout_quality_score = _clamp(
            opening_score * 0.44 + gap_quality_score * 0.24 + relative_strength_score * 0.18 + liquidity_score * 0.14,
            0.0,
            100.0,
        )
        pullback_quality_score = _clamp(
            trend_quality_score * 0.36
            + liquidity_score * 0.18
            + max(0.0, 100.0 - spread_risk_value) * 0.18
            + max(0.0, 100.0 - volatility_risk_value) * 0.28,
            0.0,
            100.0,
        )
        continuation_score = _clamp(
            opening_score * 0.36 + premarket_score * 0.20 + engine_alignment_score * 0.20 + relative_strength_score * 0.24,
            0.0,
            100.0,
        )
        open_confirmation_score = _clamp(
            opening_score * 0.55 + engine_alignment_score * 0.20 + max(0.0, 100.0 - spread_risk_value) * 0.25,
            0.0,
            100.0,
        )
        add_quality_score = _clamp(opening_score * 0.42 + premarket_score * 0.22 + confidence * 0.18 + relative_strength_score * 0.18, 0.0, 100.0)
        reduce_pressure_score = _clamp(
            (100.0 - trend_quality_score) * 0.26
            + (100.0 - relative_strength_score) * 0.24
            + volatility_risk_value * 0.24
            + (100.0 if signal == "SELL" else 20.0) * 0.26,
            0.0,
            100.0,
        )
        exit_pressure_score = _clamp(reduce_pressure_score * 0.66 + (100.0 - confidence) * 0.18 + (100.0 if signal == "SELL" else 25.0) * 0.16, 0.0, 100.0)
        news_judgment = _build_news_judgment(result=result, signal=signal, price_quality_score=stock_quality_score)

        market_context_contribution = 0.0
        if signal == "BUY":
            market_context_contribution = (
                (_safe_float(judgment.get("market_offense_level"), 50.0) - 50.0) * 0.06
                - (_safe_float(judgment.get("market_cash_preference"), 50.0) - 50.0) * 0.04
            )
        elif signal == "SELL":
            market_context_contribution = (_safe_float(judgment.get("market_defense_level"), 50.0) - 50.0) * 0.05
        market_context_contribution = round(_clamp(market_context_contribution, -8.0, 8.0), 4)

        small_cap_multiplier, tactical_small_cap_score, tactical_small_cap_allowed, small_cap_no_trade_reason = _small_cap_multiplier(
            profile,
            score=stock_quality_score,
            liquidity=liquidity_score,
            spread_risk_value=spread_risk_value,
        )
        if not bool(profile.get("us_equity_eligible", True)):
            small_cap_multiplier = min(small_cap_multiplier, 0.35)
            small_cap_no_trade_reason = small_cap_no_trade_reason or "non_us_or_non_equity_instrument"

        judgment_size_multiplier = _clamp(
            small_cap_multiplier
            * (0.92 if bool(news_judgment.get("news_requires_wait")) else 1.0)
            * (0.88 if bool(engine_conflicts_present) else 1.0)
            * _clamp(1.0 - (spread_risk_value / 260.0), 0.6, 1.1),
            0.25,
            1.25,
        )

        raw_score = (
            confidence * 0.20
            + technical_score * 0.14
            + ranking_score * 0.10
            + mtf_score * 0.09
            + trend_quality_score * 0.11
            + relative_strength_score * 0.10
            + sector_strength_score * 0.06
            + gap_quality_score * 0.05
            + liquidity_score * 0.05
            + opening_score * 0.04
            + premarket_score * 0.03
            + news_score * 0.03
            + engine_alignment_score * 0.10
            - volatility_risk_value * 0.06
        )

        if signal == "BUY":
            raw_score += 5.5
        elif signal == "SELL":
            raw_score += 2.5

        if regime_bias in {"defensive", "risk_off"} and signal == "BUY":
            raw_score *= 0.82
            premarket_score *= 0.9
            opening_score *= 0.93
        elif regime_bias == "bullish" and signal == "BUY":
            raw_score *= 1.05
            opening_score *= 1.03

        opportunity_score = round(_clamp(raw_score, 0.0, 100.0), 2)
        session_adjusted_opportunity_score = round(
            _clamp(
                opportunity_score
                + _safe_float(news_judgment.get("news_contribution_to_score"), 0.0)
                + market_context_contribution
                + (2.2 if tactical_small_cap_allowed else -2.4 if str(profile.get("market_cap_bucket") or "") == "small" else 0.0)
                - (3.0 if bool(news_judgment.get("news_requires_wait")) else 0.0)
                - (2.4 if bool(engine_conflicts_present) else 0.0),
                0.0,
                100.0,
            ),
            4,
        )
        tier = _conviction_tier(opportunity_score)
        setup_type = str(result.get("setup_type") or result.get("best_setup") or "unknown")
        expected_direction = "LONG" if signal == "BUY" else "SHORT" if signal == "SELL" else "NEUTRAL"
        preferred_candidate = "OPEN_LONG" if signal == "BUY" else "REDUCE_LONG" if signal == "SELL" else "HOLD"

        quality_flags: list[str] = []
        warning_flags: list[str] = []
        if agreement_ratio >= 0.6:
            quality_flags.append("high_model_agreement")
        if confidence >= 75:
            quality_flags.append("high_confidence")
        if gap_quality_score >= 67:
            quality_flags.append("gap_quality_strong")
        if liquidity_score >= 60:
            quality_flags.append("liquidity_supportive")
        if relative_strength_score >= 62:
            quality_flags.append("benchmark_relative_strength")
        if opening_score >= 70:
            quality_flags.append("opening_followthrough_ready")
        if premarket_score >= 68:
            quality_flags.append("premarket_structure_valid")
        if engine_alignment_score >= 70:
            quality_flags.append("engine_alignment_high")
        if stock_quality_score >= 72:
            quality_flags.append("stock_quality_high")
        if bool(news_judgment.get("news_supports_entry")):
            quality_flags.append("news_supportive")
        if bool(profile.get("tactical_small_cap_candidate")) and tactical_small_cap_allowed:
            quality_flags.append("tactical_small_cap_allowed")

        if price <= 0:
            warning_flags.append("price_unavailable")
        if signal == "HOLD":
            warning_flags.append("non_directional_signal")
        if confidence < 40:
            warning_flags.append("low_confidence")
        if spread_risk_value >= 62:
            warning_flags.append("spread_risk_elevated")
        if volatility_risk_value >= 68:
            warning_flags.append("volatility_risk_elevated")
        if liquidity_score < 42:
            warning_flags.append("liquidity_below_session_threshold")
        if engine_conflicts_present:
            warning_flags.append("engine_conflict_present")
        if small_cap_no_trade_reason:
            warning_flags.append(str(small_cap_no_trade_reason))
        for warning in (news_judgment.get("news_warning_flags") or []):
            if warning not in warning_flags:
                warning_flags.append(warning)

        opportunities.append(
            {
                "symbol": symbol,
                "strategy_mode": strategy_mode,
                "security_name": profile.get("security_name"),
                "market_cap": profile.get("market_cap"),
                "market_cap_bucket": profile.get("market_cap_bucket"),
                "listed_exchange": profile.get("exchange"),
                "us_equity_eligible": bool(profile.get("us_equity_eligible", True)),
                "is_etf": bool(profile.get("is_etf", False)),
                "analysis_signal": signal,
                "analysis_score": round(_safe_float(ensemble.get("ensemble_score"), _safe_float(row.get("analysis_score"), 0.0)), 4),
                "confidence": round(confidence, 4),
                "opportunity_score": opportunity_score,
                "session_adjusted_opportunity_score": session_adjusted_opportunity_score,
                "conviction_tier": tier,
                "expected_direction": expected_direction,
                "setup_type": setup_type,
                "preferred_action_candidate": preferred_candidate,
                "preferred_holding_horizon": "swing_2_10d",
                "risk_reward_estimate": round(risk_reward_estimate or _risk_reward_estimate(opportunity_score, signal), 4),
                "stock_quality_score": round(stock_quality_score, 4),
                "quality_flags": quality_flags,
                "warning_flags": warning_flags,
                "agreement_ratio": round(agreement_ratio, 4),
                "price": round(price, 4),
                "classic_signal": signal,
                "ranking_signal": ranking_signal,
                "classic_contribution_to_score": classic_component,
                "ranking_contribution_to_score": ranking_component,
                "engine_conflicts_present": bool(engine_conflicts_present),
                "engine_conflict_reason": engine_conflict_reason,
                "engine_alignment_score": engine_alignment_score,
                "technical_score": round(technical_score, 4),
                "ranking_score": round(ranking_score, 4),
                "multi_timeframe_score": round(mtf_score, 4),
                "relative_strength_score": round(relative_strength_score, 4),
                "sector_strength_score": round(sector_strength_score, 4),
                "gap_pct": round(gap_pct, 4),
                "gap_type": gap_type,
                "gap_quality_score": round(gap_quality_score, 4),
                "volatility_risk": _categorical_risk(volatility_risk_value),
                "volatility_risk_score": round(volatility_risk_value, 4),
                "spread_risk": _categorical_risk(spread_risk_value),
                "spread_risk_score": round(spread_risk_value, 4),
                "liquidity_score": round(liquidity_score, 4),
                "volume_ratio": round(volume_ratio, 4),
                "opening_score": round(opening_score, 4),
                "premarket_score": round(premarket_score, 4),
                "open_confirmation_score": round(open_confirmation_score, 4),
                "breakout_quality_score": round(breakout_quality_score, 4),
                "pullback_quality_score": round(pullback_quality_score, 4),
                "continuation_score": round(continuation_score, 4),
                "fade_risk": round(_clamp(100.0 - continuation_score + max(abs(gap_pct) - 1.0, 0.0) * 8.0, 0.0, 100.0), 4),
                "add_quality_score": round(add_quality_score, 4),
                "reduce_pressure_score": round(reduce_pressure_score, 4),
                "exit_pressure_score": round(exit_pressure_score, 4),
                "news_score": round(news_score, 4),
                "news_relevance_score": news_judgment.get("news_relevance_score"),
                "news_sentiment_score": news_judgment.get("news_sentiment_score"),
                "news_strength_score": news_judgment.get("news_strength_score"),
                "catalyst_type": news_judgment.get("catalyst_type"),
                "catalyst_horizon": news_judgment.get("catalyst_horizon"),
                "catalyst_scope": news_judgment.get("catalyst_scope"),
                "catalyst_alignment_with_price": news_judgment.get("catalyst_alignment_with_price"),
                "news_confidence": news_judgment.get("news_confidence"),
                "news_warning_flags": news_judgment.get("news_warning_flags"),
                "news_action_bias": news_judgment.get("news_action_bias"),
                "news_supports_entry": news_judgment.get("news_supports_entry"),
                "news_supports_add": news_judgment.get("news_supports_add"),
                "news_supports_reduce": news_judgment.get("news_supports_reduce"),
                "news_supports_exit": news_judgment.get("news_supports_exit"),
                "news_requires_wait": news_judgment.get("news_requires_wait"),
                "news_no_trade_reason": news_judgment.get("news_no_trade_reason"),
                "news_contribution_to_score": news_judgment.get("news_contribution_to_score"),
                "market_context_contribution_to_score": market_context_contribution,
                "judgment_size_multiplier": round(judgment_size_multiplier, 4),
                "volatility20": round(volatility20, 4),
                "atr14": round(atr14, 4),
                "tactical_small_cap_candidate": bool(profile.get("tactical_small_cap_candidate", False)),
                "tactical_small_cap_score": round(tactical_small_cap_score, 4),
                "tactical_small_cap_allowed": bool(tactical_small_cap_allowed),
                "small_cap_liquidity_quality": "strong" if liquidity_score >= 62 else "acceptable" if liquidity_score >= 48 else "weak",
                "small_cap_spread_risk": _categorical_risk(spread_risk_value),
                "small_cap_catalyst_quality": round(_clamp(_safe_float(news_judgment.get("news_strength_score"), 0.0) * 0.58 + _safe_float(news_judgment.get("news_relevance_score"), 0.0) * 0.42, 0.0, 100.0), 4),
                "small_cap_position_size_multiplier": round(small_cap_multiplier, 4),
                "small_cap_no_trade_reason": small_cap_no_trade_reason,
                "ensemble_components_available": [
                    key for key, value in {
                        "classic": True,
                        "ranking": True,
                        "ml": bool(ml_output),
                        "dl": bool(dl_output),
                    }.items()
                    if value
                ],
                "ensemble_components_used": [
                    key for key, value in {
                        "classic": signal in {"BUY", "SELL", "HOLD"},
                        "ranking": ranking_signal in {"BUY", "SELL", "HOLD"},
                        "ml": ml_signal in {"BUY", "SELL"},
                        "dl": dl_signal in {"BUY", "SELL"},
                    }.items()
                    if value
                ],
            }
        )

    opportunities.sort(key=lambda item: float(item.get("session_adjusted_opportunity_score") or item.get("opportunity_score") or 0.0), reverse=True)
    for rank, row in enumerate(opportunities, start=1):
        row["portfolio_priority_rank"] = rank

    return opportunities


def _execution_priority_band_for_action(
    *,
    action: str,
    score: float,
    reason_code: str,
    funded: bool,
    funded_partially: bool = False,
) -> str:
    normalized_action = str(action or "").strip().upper()
    reason = str(reason_code or "").strip().lower()

    if normalized_action == "EXIT_LONG":
        if reason in {"exit_due_to_risk", "exit_due_to_thesis_break"}:
            return "critical"
        return "high"
    if normalized_action == "REDUCE_LONG":
        if reason in {"reduce_due_to_better_use_of_capital", "reduce_due_to_regime_defensive", "reduce_due_to_overconcentration"}:
            return "high"
        return "normal"
    if normalized_action in {"OPEN_LONG", "ADD_LONG"}:
        if not funded:
            return "deferred"
        if score >= 86:
            return "high"
        if funded_partially:
            return "normal"
        if score >= 64:
            return "normal"
        return "low"
    if normalized_action in {"NONE", "HOLD", ""}:
        return "deferred"
    return "low"


def _legacy_priority_from_band(band: str) -> str:
    normalized = str(band or "").strip().lower()
    if normalized in {"critical", "high"}:
        return "high"
    if normalized == "normal":
        return "normal"
    return "low"


def _symbol_decision(
    *,
    opportunity: dict,
    held_positions: dict[str, dict],
    portfolio_value: float,
    available_cash: float,
    reserve_cash: float,
    remaining_new_positions: int,
    auto_config: dict,
    regime: dict,
    market_open: bool,
) -> tuple[dict, float, int]:
    symbol = str(opportunity.get("symbol") or "").upper()
    signal = _normalize_signal(opportunity.get("analysis_signal"))
    score = _safe_float(opportunity.get("session_adjusted_opportunity_score"), _safe_float(opportunity.get("opportunity_score"), 0.0))
    confidence = _safe_float(opportunity.get("confidence"), 0.0)
    price = max(_safe_float(opportunity.get("price"), 0.0), 0.0)
    judgment_size_multiplier = _clamp(_safe_float(opportunity.get("judgment_size_multiplier"), 1.0), 0.25, 1.5)

    held_row = held_positions.get(symbol, {}) if isinstance(held_positions, dict) else {}
    current_side = str(held_row.get("side") or "").upper()
    current_qty = max(_safe_float(held_row.get("quantity"), 0.0), 0.0)
    has_open_long = current_side == "LONG" and current_qty > 0

    max_position_pct = _clamp(
        _safe_float(auto_config.get("portfolio_max_position_pct"), _safe_float(auto_config.get("add_long_max_position_pct"), 8.0)),
        0.5,
        40.0,
    )
    risk_multiplier = _clamp(_safe_float(regime.get("risk_multiplier"), 1.0), 0.1, 2.0)
    target_position_pct = _clamp(max_position_pct * (score / 100.0) * risk_multiplier * judgment_size_multiplier, 0.0, max_position_pct)

    current_value = current_qty * price if price > 0 else 0.0
    current_pct = (current_value / portfolio_value * 100.0) if portfolio_value > 0 else 0.0
    target_value = portfolio_value * target_position_pct / 100.0 if portfolio_value > 0 else 0.0
    desired_delta_value = target_value - current_value
    desired_delta_pct = target_position_pct - current_pct

    min_notional = max(_safe_float(auto_config.get("add_long_min_notional"), 100.0), 0.0)
    min_shares = max(_safe_float(auto_config.get("add_long_min_shares"), 1.0), 0.0)
    min_score = _clamp(_safe_float(auto_config.get("opportunity_min_score"), 56.0), 0.0, 100.0)
    add_min_conf = _clamp(_safe_float(auto_config.get("add_long_min_confidence"), 0.0), 0.0, 100.0)
    add_min_score = _clamp(_safe_float(auto_config.get("add_long_min_score"), 0.0), 0.0, 1.0)
    add_enabled = bool(auto_config.get("add_long_enabled", True))
    reduce_enabled = bool(auto_config.get("reduce_long_enabled", True))
    exit_enabled = bool(auto_config.get("exit_on_thesis_break", True))
    reduce_on_regime_defensive = bool(auto_config.get("reduce_on_regime_defensive", True))

    planned_action = "HOLD"
    decision_reason_code = "hold_position_valid"
    decision_reason_detail = "No portfolio action required for this symbol in this cycle."
    proposed_qty = 0.0
    capital_requested_value = 0.0
    capital_competition_reason = None
    better_use_of_capital_reason = None
    replacement_candidate = None
    displaced_symbol = None

    if has_open_long:
        if signal == "BUY":
            score_abs = abs(_safe_float(opportunity.get("analysis_score"), 0.0))
            if not bool(regime.get("add_allowed", True)):
                planned_action = "HOLD"
                decision_reason_code = "reduce_due_to_regime_defensive" if bool(regime.get("reduce_bias")) else "existing_long_position_no_add"
                decision_reason_detail = "Regime policy suppressed add-to-existing-long in this cycle."
            elif not add_enabled:
                planned_action = "HOLD"
                decision_reason_code = "existing_long_position_no_add"
                decision_reason_detail = "Add-to-existing-long disabled in runtime settings."
            elif confidence < max(min_score, add_min_conf) or score_abs < add_min_score:
                planned_action = "HOLD"
                decision_reason_code = "insufficient_add_conviction"
                decision_reason_detail = "Opportunity score/confidence below add threshold."
            elif desired_delta_value <= 0.0 or desired_delta_pct <= 0.02:
                planned_action = "HOLD"
                decision_reason_code = "at_target_position_size"
                decision_reason_detail = "Current LONG size is already at/above target allocation."
            elif price <= 0:
                planned_action = "HOLD"
                decision_reason_code = "add_price_unavailable"
                decision_reason_detail = "Cannot size ADD_LONG because price is unavailable."
            else:
                proposed_qty = float(int(max(desired_delta_value / price, 0.0))) if price > 0 else 0.0
                proposed_notional = proposed_qty * price
                if proposed_qty < max(min_shares, 1.0) or proposed_notional < min_notional:
                    planned_action = "HOLD"
                    decision_reason_code = "add_qty_below_minimum"
                    decision_reason_detail = "Computed add quantity does not meet minimum notional/share limits."
                else:
                    planned_action = "ADD_LONG"
                    decision_reason_code = "add_long_allowed"
                    decision_reason_detail = "Existing LONG is below target; candidate add request prepared for allocator competition."
                    capital_requested_value = proposed_notional
        elif signal == "SELL":
            if exit_enabled and (score < 45.0 or confidence < 35.0):
                planned_action = "EXIT_LONG"
                decision_reason_code = "exit_due_to_thesis_break"
                decision_reason_detail = "SELL signal with weak confidence triggered thesis-break exit."
                proposed_qty = current_qty
            elif reduce_enabled:
                planned_action = "REDUCE_LONG"
                decision_reason_code = "reduce_due_to_weaker_rank"
                decision_reason_detail = "SELL signal triggered a defensive trim of the existing LONG."
                proposed_qty = max(float(int(current_qty * 0.5)), 1.0)
            else:
                planned_action = "HOLD"
                decision_reason_code = "hold_position_valid"
                decision_reason_detail = "Reduce/exit actions disabled by runtime settings."
        else:
            if bool(regime.get("reduce_bias")) and reduce_on_regime_defensive and reduce_enabled and current_pct > target_position_pct + 0.35:
                planned_action = "REDUCE_LONG"
                decision_reason_code = "reduce_due_to_regime_defensive"
                decision_reason_detail = "Defensive regime reduced an oversized long concentration."
                proposed_qty = max(float(int(current_qty * 0.35)), 1.0)
            else:
                planned_action = "HOLD"
                decision_reason_code = "hold_position_valid"
                decision_reason_detail = "Position still valid under current conviction/regime constraints."
    else:
        if signal == "BUY":
            if score < min_score:
                planned_action = "HOLD"
                decision_reason_code = "insufficient_add_conviction"
                decision_reason_detail = "Opportunity score is below minimum entry threshold."
            elif price <= 0:
                planned_action = "HOLD"
                decision_reason_code = "add_price_unavailable"
                decision_reason_detail = "Price unavailable; cannot size new position."
            else:
                open_budget = max(target_value, min_notional)
                proposed_qty = float(int(max(open_budget / price, 0.0))) if price > 0 else 0.0
                proposed_notional = proposed_qty * price
                if proposed_qty < max(min_shares, 1.0) or proposed_notional < min_notional:
                    planned_action = "HOLD"
                    decision_reason_code = "add_qty_below_minimum"
                    decision_reason_detail = "New position sizing fell below minimum notional/share threshold."
                else:
                    planned_action = "OPEN_LONG"
                    decision_reason_code = "open_long_allowed"
                    decision_reason_detail = "Opportunity is eligible for allocator competition."
                    capital_requested_value = proposed_notional
        else:
            planned_action = "HOLD"
            decision_reason_code = "no_action_from_signal"
            decision_reason_detail = "No actionable LONG setup from current signal."

    requested_execution_action = planned_action if planned_action in _EXECUTION_ACTIONS else None
    execution_skip_reason = "market_closed" if requested_execution_action and not market_open else None
    initial_priority_band = _execution_priority_band_for_action(
        action=requested_execution_action or planned_action,
        score=score,
        reason_code=decision_reason_code,
        funded=False,
    )
    execution_priority = _legacy_priority_from_band(initial_priority_band)
    order_style_preference = "market" if initial_priority_band in {"critical", "high"} else "limit"
    session_quality = "closed" if not market_open else "normal"
    estimated_slippage_risk = "high" if price <= 0 else "medium" if score >= 80 else "low"

    requested_order_qty = round(max(proposed_qty, 0.0), 4)
    capital_requested_value = round(max(capital_requested_value, 0.0), 4)

    decision = {
        **opportunity,
        "has_open_long": bool(has_open_long),
        "current_position_side": "LONG" if has_open_long else None,
        "current_position_qty": round(current_qty, 4),
        "current_position_value": round(current_value, 4),
        "current_position_pct": round(current_pct, 4),
        "target_position_pct": round(target_position_pct, 4),
        "target_position_value": round(target_value, 4),
        "desired_delta_pct": round(desired_delta_pct, 4),
        "desired_delta_value": round(desired_delta_value, 4),
        "proposed_order_qty": requested_order_qty,
        "requested_order_qty": requested_order_qty,
        "approved_order_qty": 0.0,
        "approved_position_pct": round(current_pct, 4),
        "planned_execution_action": requested_execution_action,
        "requested_execution_action": requested_execution_action,
        "action_decision": planned_action,
        "decision_outcome_code": decision_reason_code,
        "decision_outcome_detail": decision_reason_detail,
        "capital_competition_reason": capital_competition_reason,
        "better_use_of_capital_reason": better_use_of_capital_reason,
        "replacement_candidate": replacement_candidate,
        "displaced_symbol": displaced_symbol,
        "capital_requested_value": capital_requested_value,
        "capital_approved_value": 0.0,
        "funding_ratio": 0.0,
        "remaining_unfunded_value": capital_requested_value,
        "funded_partially": False,
        "partial_funding_applied": False,
        "partial_funding_reason": None,
        "funding_status": "pending" if requested_execution_action in {"OPEN_LONG", "ADD_LONG"} else "unfunded",
        "capital_reserved_value": round(max(reserve_cash, 0.0), 4),
        "funded": False,
        "funding_decision": "pending_allocator" if requested_execution_action in {"OPEN_LONG", "ADD_LONG"} else "not_applicable",
        "portfolio_slot_required": 1 if requested_execution_action == "OPEN_LONG" else 0,
        "portfolio_slot_consumed": 0,
        "portfolio_slot_available": max(int(remaining_new_positions), 0),
        "available_cash_before": round(max(available_cash, 0.0), 4),
        "available_cash_after": round(max(available_cash, 0.0), 4),
        "regime_adjusted_budget": 0.0,
        "funding_rank": _safe_int(opportunity.get("portfolio_priority_rank"), 0) or None,
        "cash_reservation_pct": round((_safe_float(auto_config.get("portfolio_cash_reserve_pct"), 20.0)), 2),
        "execution_priority_band": initial_priority_band,
        "execution_priority": execution_priority,
        "order_style_preference": order_style_preference,
        "session_quality": session_quality,
        "execution_skip_reason": execution_skip_reason,
        "estimated_slippage_risk": estimated_slippage_risk,
    }

    return decision, available_cash, remaining_new_positions


def plan_portfolio_actions(
    *,
    opportunities: list[dict],
    held_positions: dict[str, dict],
    portfolio_summary: dict | None,
    auto_trading_config: dict | None,
    regime: dict,
    market_open: bool,
) -> dict:
    config = auto_trading_config if isinstance(auto_trading_config, dict) else {}
    summary = portfolio_summary if isinstance(portfolio_summary, dict) else {}

    portfolio_value = max(_safe_float(summary.get("total_equity") or summary.get("portfolio_value"), 0.0), 0.0)
    cash_balance = max(_safe_float(summary.get("cash_balance"), 0.0), 0.0)
    reserve_pct = _clamp(_safe_float(config.get("portfolio_cash_reserve_pct"), 20.0), 0.0, 95.0)
    reserve_cash = portfolio_value * reserve_pct / 100.0 if portfolio_value > 0 else cash_balance * reserve_pct / 100.0

    configured_new_positions = max(_safe_int(config.get("portfolio_max_new_positions"), 2), 0)
    regime_new_positions = max(_safe_int(regime.get("max_new_positions"), configured_new_positions), 0)
    max_new_positions = min(configured_new_positions, regime_new_positions)
    slots_remaining = max_new_positions

    gross_long = max(_safe_float(summary.get("long_market_value"), _safe_float(summary.get("total_market_value"), 0.0)), 0.0)
    gross_short = abs(_safe_float(summary.get("short_market_value"), 0.0))
    gross_now = gross_long + gross_short

    regime_gross_pct = _clamp(_safe_float(regime.get("max_gross_exposure_pct"), _safe_float(config.get("portfolio_max_gross_exposure_pct"), 100.0)), 0.0, 100.0)
    max_gross_value = portfolio_value * regime_gross_pct / 100.0 if portfolio_value > 0 else 0.0
    gross_headroom = max(max_gross_value - gross_now, 0.0) if max_gross_value > 0 else 0.0

    available_cash_before = cash_balance
    base_allocatable_cash = max(cash_balance - reserve_cash, 0.0)
    if portfolio_value > 0 and max_gross_value > 0:
        regime_adjusted_budget = min(base_allocatable_cash, gross_headroom)
    else:
        regime_adjusted_budget = base_allocatable_cash
    remaining_budget = max(regime_adjusted_budget, 0.0)

    decisions: list[dict] = []
    decision_map: dict[str, dict] = {}
    for opportunity in opportunities:
        decision, _, _ = _symbol_decision(
            opportunity=opportunity,
            held_positions=held_positions,
            portfolio_value=portfolio_value,
            available_cash=available_cash_before,
            reserve_cash=reserve_cash,
            remaining_new_positions=max_new_positions,
            auto_config=config,
            regime=regime,
            market_open=market_open,
        )
        decision["regime_adjusted_budget"] = round(regime_adjusted_budget, 4)
        decisions.append(decision)
        symbol = str(decision.get("symbol") or "").upper()
        if symbol:
            decision_map[symbol] = decision

    max_position_pct = _clamp(_safe_float(config.get("portfolio_max_position_pct"), _safe_float(config.get("add_long_max_position_pct"), 8.0)), 0.5, 40.0)
    min_score = _clamp(_safe_float(config.get("opportunity_min_score"), 56.0), 0.0, 100.0)
    min_shares = max(_safe_float(config.get("add_long_min_shares"), 1.0), 1.0)
    partial_funding_enabled = bool(config.get("partial_funding_enabled", True))
    min_partial_funding_notional = max(
        _safe_float(config.get("min_partial_funding_notional"), max(_safe_float(config.get("add_long_min_notional"), 100.0), 100.0)),
        0.0,
    )
    min_partial_funding_ratio = _clamp(_safe_float(config.get("min_partial_funding_ratio"), 0.30), 0.05, 1.0)
    partial_funding_top_rank_only = bool(config.get("partial_funding_top_rank_only", False))

    replacement_events: list[dict] = []
    displaced_symbols: set[str] = set()

    def _mark_not_funded(row: dict, *, code: str, detail: str, competition_reason: str, better_use: str | None = None) -> None:
        planned_action = str(row.get("planned_execution_action") or row.get("requested_execution_action") or row.get("action_decision") or "HOLD").upper()
        requested_value = round(max(_safe_float(row.get("capital_requested_value"), 0.0), 0.0), 4)

        row["planned_execution_action"] = planned_action if planned_action in _EXECUTION_ACTIONS else None
        row["requested_execution_action"] = None
        row["action_decision"] = "HOLD"
        row["funded"] = False
        row["funded_partially"] = False
        row["partial_funding_applied"] = False
        row["partial_funding_reason"] = code if code.startswith("skipped") else None
        row["funding_status"] = "unfunded"
        row["funding_decision"] = code
        row["capital_approved_value"] = 0.0
        row["funding_ratio"] = 0.0
        row["remaining_unfunded_value"] = requested_value
        row["approved_order_qty"] = 0.0
        row["approved_position_pct"] = round(_safe_float(row.get("current_position_pct"), 0.0), 4)
        row["decision_outcome_code"] = code
        row["decision_outcome_detail"] = detail
        row["capital_competition_reason"] = competition_reason
        row["better_use_of_capital_reason"] = better_use
        row["execution_skip_reason"] = "allocator_not_funded"
        row["portfolio_slot_consumed"] = 0

        priority_band = _execution_priority_band_for_action(
            action=planned_action,
            score=_safe_float(row.get("opportunity_score"), 0.0),
            reason_code=code,
            funded=False,
        )
        row["execution_priority_band"] = priority_band
        row["execution_priority"] = _legacy_priority_from_band(priority_band)

    def _select_displacement_target(request_row: dict) -> tuple[dict | None, str | None, float]:
        request_symbol = str(request_row.get("symbol") or "").upper()
        request_score = _safe_float(request_row.get("opportunity_score"), 0.0)
        candidates: list[tuple[float, float, float, dict]] = []
        for donor in decisions:
            donor_symbol = str(donor.get("symbol") or "").upper()
            if not donor_symbol or donor_symbol == request_symbol or donor_symbol in displaced_symbols:
                continue
            if not bool(donor.get("has_open_long")):
                continue
            donor_action = str(donor.get("action_decision") or "").upper()
            donor_requested = str(donor.get("requested_execution_action") or "").upper()
            if donor_action not in {"HOLD", "ADD_LONG"} and donor_requested not in {"", "NONE", "HOLD", "ADD_LONG"}:
                continue
            donor_value = max(_safe_float(donor.get("current_position_value"), 0.0), 0.0)
            if donor_value <= 0.0:
                continue
            donor_score = _safe_float(donor.get("opportunity_score"), 0.0)
            score_advantage = request_score - donor_score
            if score_advantage < 7.0:
                continue
            candidates.append((score_advantage, donor_value, donor_score, donor))

        if not candidates:
            return None, None, 0.0

        candidates.sort(key=lambda item: (item[0], item[1], -item[2]), reverse=True)
        _, donor_value, donor_score, donor = candidates[0]

        if donor_score < max(min_score * 0.82, 42.0):
            action = "EXIT_LONG"
            freed_value = donor_value
            donor_qty = max(_safe_float(donor.get("current_position_qty"), 0.0), 0.0)
        else:
            action = "REDUCE_LONG"
            freed_value = donor_value * 0.5
            donor_qty = max(float(int(max(_safe_float(donor.get("current_position_qty"), 0.0) * 0.5, 1.0))), 1.0)

        displaced_symbols.add(str(donor.get("symbol") or "").upper())
        donor["planned_execution_action"] = action
        donor["requested_execution_action"] = action
        donor["action_decision"] = action
        donor["proposed_order_qty"] = round(donor_qty, 4)
        donor["requested_order_qty"] = round(donor_qty, 4)
        donor["approved_order_qty"] = round(donor_qty, 4)
        donor["funded"] = False
        donor["funded_partially"] = False
        donor["partial_funding_applied"] = False
        donor["funding_status"] = "not_applicable"
        donor["funding_decision"] = "replacement_selected"
        donor["decision_outcome_code"] = "exit_due_to_replacement" if action == "EXIT_LONG" else "reduce_due_to_better_use_of_capital"
        donor["decision_outcome_detail"] = (
            f"Capital was reallocated from {donor.get('symbol')} to a stronger opportunity {request_row.get('symbol')}."
        )
        donor["capital_competition_reason"] = "capital_reallocated_to_higher_rank"
        donor["better_use_of_capital_reason"] = (
            f"{request_row.get('symbol')} score {request_score:.2f} exceeded {donor.get('symbol')} score {donor_score:.2f}."
        )
        donor["replacement_candidate"] = request_row.get("symbol")
        donor["displaced_symbol"] = donor.get("symbol")
        donor["portfolio_slot_consumed"] = 0
        donor_priority = _execution_priority_band_for_action(
            action=action,
            score=donor_score,
            reason_code=donor.get("decision_outcome_code"),
            funded=False,
        )
        donor["execution_priority_band"] = donor_priority
        donor["execution_priority"] = _legacy_priority_from_band(donor_priority)

        replacement_events.append(
            {
                "replacement_candidate": request_row.get("symbol"),
                "displaced_symbol": donor.get("symbol"),
                "replacement_action": action,
                "freed_capital_value": round(freed_value, 4),
                "request_score": round(request_score, 4),
                "displaced_score": round(donor_score, 4),
                "reason": donor.get("decision_outcome_code"),
            }
        )

        return donor, action, freed_value

    # Pre-credit capital expected from explicit reducer/exit decisions (sell-side intents).
    for row in decisions:
        action = str(row.get("requested_execution_action") or "").upper()
        if action not in {"REDUCE_LONG", "EXIT_LONG"}:
            continue
        current_value = max(_safe_float(row.get("current_position_value"), 0.0), 0.0)
        freed = current_value if action == "EXIT_LONG" else current_value * 0.5
        if freed <= 0:
            continue
        remaining_budget += freed
        row["funding_decision"] = "capital_source_exit" if action == "EXIT_LONG" else "capital_source_reduce"
        row["funding_status"] = "not_applicable"
        row["capital_competition_reason"] = "capital_recycled_from_existing_positions"
        row["requested_order_qty"] = round(max(_safe_float(row.get("proposed_order_qty"), 0.0), 0.0), 4)
        row["approved_order_qty"] = round(max(_safe_float(row.get("proposed_order_qty"), 0.0), 0.0), 4)
        row["approved_position_pct"] = round(
            0.0 if action == "EXIT_LONG" else max(_safe_float(row.get("current_position_pct"), 0.0) * 0.5, 0.0),
            4,
        )
        priority_band = _execution_priority_band_for_action(
            action=action,
            score=_safe_float(row.get("opportunity_score"), 0.0),
            reason_code=str(row.get("decision_outcome_code") or ""),
            funded=False,
        )
        row["execution_priority_band"] = priority_band
        row["execution_priority"] = _legacy_priority_from_band(priority_band)

    requests = [
        row
        for row in decisions
        if str(row.get("requested_execution_action") or "").upper() in {"OPEN_LONG", "ADD_LONG"}
    ]
    requests.sort(
        key=lambda row: (
            _safe_float(row.get("opportunity_score"), 0.0),
            -_safe_int(row.get("portfolio_priority_rank"), 0),
        ),
        reverse=True,
    )

    for row in requests:
        symbol = str(row.get("symbol") or "").upper()
        action = str(row.get("requested_execution_action") or "").upper()
        requested_value = max(_safe_float(row.get("capital_requested_value"), 0.0), 0.0)
        row["available_cash_before"] = round(remaining_budget + reserve_cash, 4)
        row["regime_adjusted_budget"] = round(regime_adjusted_budget, 4)

        if action == "ADD_LONG" and not bool(regime.get("add_allowed", True)):
            _mark_not_funded(
                row,
                code="skipped_due_to_regime",
                detail="Regime disabled adding to existing positions in this cycle.",
                competition_reason="regime_add_disabled",
                better_use="regime_defensive_cash_priority",
            )
            row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)
            continue

        if action == "OPEN_LONG" and max_new_positions <= 0:
            _mark_not_funded(
                row,
                code="skipped_due_to_regime",
                detail="Regime allows zero new positions in this cycle.",
                competition_reason="regime_new_positions_zero",
                better_use="regime_defensive_cash_priority",
            )
            row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)
            continue

        if requested_value <= 0.0:
            _mark_not_funded(
                row,
                code="add_qty_below_minimum",
                detail="Requested capital is below operational minimums.",
                competition_reason="allocation_request_invalid",
            )
            row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)
            continue

        if _safe_float(row.get("target_position_pct"), 0.0) > max_position_pct + 1e-6:
            _mark_not_funded(
                row,
                code="skipped_due_to_concentration",
                detail="Target size exceeds max position concentration policy.",
                competition_reason="max_position_pct_breached",
                better_use="concentration_cap_enforced",
            )
            row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)
            continue

        slot_required = 1 if action == "OPEN_LONG" else 0
        if slot_required and slots_remaining <= 0:
            donor, donor_action, freed = _select_displacement_target(row)
            if donor is not None and donor_action == "EXIT_LONG":
                slots_remaining += 1
            if donor is not None and freed > 0:
                remaining_budget += freed
                row["replacement_candidate"] = str(row.get("symbol") or "")
                row["displaced_symbol"] = donor.get("symbol")
                row["capital_competition_reason"] = "replacement_selected"
                row["better_use_of_capital_reason"] = (
                    f"Displaced {donor.get('symbol')} to create slot/capital for higher-ranked idea {symbol}."
                )

        if requested_value > remaining_budget + 1e-6:
            donor, _, freed = _select_displacement_target(row)
            if donor is not None and freed > 0:
                remaining_budget += freed
                row["replacement_candidate"] = str(row.get("symbol") or "")
                row["displaced_symbol"] = donor.get("symbol")
                row["capital_competition_reason"] = "replacement_selected"
                row["better_use_of_capital_reason"] = (
                    f"Freed capital from {donor.get('symbol')} for higher-ranked idea {symbol}."
                )

        if slot_required and slots_remaining <= 0:
            _mark_not_funded(
                row,
                code="skipped_lower_rank",
                detail="No portfolio slot remained after higher-ranked symbols consumed capacity.",
                competition_reason="portfolio_slots_exhausted",
                better_use="higher_rank_symbols_funded_first",
            )
            row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)
            continue

        approved_value = requested_value
        approved_qty = max(_safe_float(row.get("requested_order_qty"), _safe_float(row.get("proposed_order_qty"), 0.0)), 0.0)
        partial_reason = None
        funded_partially = False

        if requested_value > remaining_budget + 1e-6:
            can_attempt_partial = (
                partial_funding_enabled
                and remaining_budget > 0.0
                and (not partial_funding_top_rank_only or _safe_int(row.get("portfolio_priority_rank"), 0) <= 1)
            )
            if not can_attempt_partial:
                if reserve_cash > 0 and (remaining_budget <= 0.0 or cash_balance - reserve_cash <= 0.0):
                    code = "skipped_cash_reserved"
                    detail = "Allocator preserved cash reserve and deferred this lower-priority request."
                    comp = "cash_reserve_policy"
                    better = "cash_preservation_priority"
                else:
                    code = "skipped_due_to_better_existing_use"
                    detail = "Capital allocated to higher-ranked ideas or existing positions with better utility."
                    comp = "higher_priority_symbols_funded_first"
                    better = "better_existing_use_of_capital"
                _mark_not_funded(
                    row,
                    code=code,
                    detail=detail,
                    competition_reason=comp,
                    better_use=better,
                )
                row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)
                continue

            price_for_qty = max(_safe_float(row.get("price"), 0.0), 0.0)
            tentative_approved = min(requested_value, remaining_budget)
            if price_for_qty > 0:
                approved_qty = float(int(max(tentative_approved / price_for_qty, 0.0)))
                approved_value = approved_qty * price_for_qty
            else:
                ratio_for_qty = (tentative_approved / requested_value) if requested_value > 0 else 0.0
                approved_qty = max(
                    _safe_float(row.get("requested_order_qty"), _safe_float(row.get("proposed_order_qty"), 0.0)) * ratio_for_qty,
                    0.0,
                )
                approved_value = tentative_approved

            funding_ratio = approved_value / requested_value if requested_value > 0 else 0.0
            if approved_value < min_partial_funding_notional or funding_ratio < min_partial_funding_ratio or approved_qty < min_shares:
                _mark_not_funded(
                    row,
                    code="skipped_due_to_min_partial_size",
                    detail="Remaining capital was below partial-funding thresholds (ratio/notional/qty).",
                    competition_reason="partial_size_below_threshold",
                    better_use="avoid_tiny_noisy_orders",
                )
                row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)
                continue

            funded_partially = approved_value + 1e-6 < requested_value
            partial_reason = "limited_remaining_budget"

        remaining_budget = max(remaining_budget - approved_value, 0.0)
        if slot_required:
            slots_remaining = max(slots_remaining - 1, 0)

        row["funded"] = True
        row["funded_partially"] = bool(funded_partially)
        row["partial_funding_applied"] = bool(funded_partially)
        row["partial_funding_reason"] = partial_reason if funded_partially else None
        row["funding_status"] = "partially_funded" if funded_partially else "fully_funded"
        row["capital_approved_value"] = round(approved_value, 4)
        row["funding_ratio"] = round((approved_value / requested_value) if requested_value > 0 else 0.0, 4)
        row["remaining_unfunded_value"] = round(max(requested_value - approved_value, 0.0), 4)
        row["approved_order_qty"] = round(max(approved_qty, 0.0), 4)
        if row.get("approved_order_qty", 0) > 0:
            row["proposed_order_qty"] = row["approved_order_qty"]
        row["approved_position_pct"] = round(
            _safe_float(row.get("current_position_pct"), 0.0) + ((approved_value / portfolio_value) * 100.0 if portfolio_value > 0 else 0.0),
            4,
        )
        row["capital_competition_reason"] = row.get("capital_competition_reason") or ("partial_funding_remaining_budget" if funded_partially else "won_priority_allocation")
        row["funding_decision"] = (
            "replacement_selected_partial"
            if funded_partially and row.get("displaced_symbol")
            else (
                "replacement_selected"
                if row.get("displaced_symbol")
                else ("funded_partially" if funded_partially else "funded_full")
            )
        )
        row["portfolio_slot_consumed"] = slot_required
        row["portfolio_slot_available"] = slots_remaining
        row["decision_outcome_code"] = "open_long_allowed" if action == "OPEN_LONG" else "add_long_allowed"
        if action == "OPEN_LONG" and funded_partially:
            row["decision_outcome_detail"] = "Allocator partially funded this new position due to remaining cycle budget."
        elif action == "OPEN_LONG":
            row["decision_outcome_detail"] = "Allocator fully funded this new position after rank/constraint competition."
        elif funded_partially:
            row["decision_outcome_detail"] = "Allocator partially funded this add request due to remaining cycle budget."
        else:
            row["decision_outcome_detail"] = "Allocator fully funded this add request based on rank and remaining capacity."
        row["execution_skip_reason"] = "market_closed" if row.get("requested_execution_action") and not market_open else None

        priority_band = _execution_priority_band_for_action(
            action=action,
            score=_safe_float(row.get("opportunity_score"), 0.0),
            reason_code=row.get("decision_outcome_code"),
            funded=True,
            funded_partially=bool(funded_partially),
        )
        row["execution_priority_band"] = priority_band
        row["execution_priority"] = _legacy_priority_from_band(priority_band)
        row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)

    for row in decisions:
        if "available_cash_after" not in row:
            row["available_cash_after"] = round(remaining_budget + reserve_cash, 4)
        if "portfolio_slot_available" not in row:
            row["portfolio_slot_available"] = slots_remaining

        requested_value = max(_safe_float(row.get("capital_requested_value"), 0.0), 0.0)
        approved_value = max(_safe_float(row.get("capital_approved_value"), 0.0), 0.0)
        if "remaining_unfunded_value" not in row:
            row["remaining_unfunded_value"] = round(max(requested_value - approved_value, 0.0), 4)
        if "funding_ratio" not in row:
            row["funding_ratio"] = round((approved_value / requested_value) if requested_value > 0 else 0.0, 4)
        if "approved_order_qty" not in row:
            row["approved_order_qty"] = round(max(_safe_float(row.get("proposed_order_qty"), 0.0), 0.0), 4) if approved_value > 0 else 0.0
        if "approved_position_pct" not in row:
            row["approved_position_pct"] = round(_safe_float(row.get("current_position_pct"), 0.0), 4)
        if "funding_status" not in row:
            if row.get("funded"):
                row["funding_status"] = "partially_funded" if bool(row.get("funded_partially")) else "fully_funded"
            else:
                row["funding_status"] = "unfunded"

        action = str(row.get("action_decision") or "HOLD").upper()
        if action in {"REDUCE_LONG", "EXIT_LONG"}:
            if row.get("funding_decision") in {None, "not_applicable", "pending_allocator"}:
                row["funding_decision"] = "reduction_selected" if action == "REDUCE_LONG" else "exit_selected"
                row["capital_competition_reason"] = row.get("capital_competition_reason") or "risk_or_regime_rebalance"
            row["funding_status"] = "not_applicable"
            if _safe_float(row.get("approved_order_qty"), 0.0) <= 0:
                row["approved_order_qty"] = round(max(_safe_float(row.get("proposed_order_qty"), 0.0), 0.0), 4)

        if action == "HOLD" and not row.get("capital_competition_reason"):
            row["capital_competition_reason"] = "hold_no_better_use_of_capital" if row.get("has_open_long") else row.get("decision_outcome_code")

        priority_band = _execution_priority_band_for_action(
            action=action,
            score=_safe_float(row.get("opportunity_score"), 0.0),
            reason_code=str(row.get("decision_outcome_code") or ""),
            funded=bool(row.get("funded")),
            funded_partially=bool(row.get("funded_partially")),
        )
        row["execution_priority_band"] = str(row.get("execution_priority_band") or priority_band)
        row["execution_priority"] = _legacy_priority_from_band(row["execution_priority_band"])

    action_counts: Counter[str] = Counter(str(item.get("action_decision") or "HOLD") for item in decisions)
    reason_counts: Counter[str] = Counter(str(item.get("decision_outcome_code") or "unknown") for item in decisions)
    competition_reason_counts: Counter[str] = Counter(
        str(item.get("capital_competition_reason") or "unknown") for item in decisions
    )

    funded_rows = [
        row for row in decisions
        if bool(row.get("funded")) and str(row.get("requested_execution_action") or "").upper() in {"OPEN_LONG", "ADD_LONG"}
    ]
    funded_symbols = [str(row.get("symbol") or "") for row in funded_rows if row.get("symbol")]

    buy_candidates = [row for row in decisions if str(row.get("analysis_signal") or "").upper() == "BUY"]
    unfunded_buy_candidates = [
        row for row in buy_candidates
        if not bool(row.get("funded")) and str(row.get("planned_execution_action") or "").upper() in {"OPEN_LONG", "ADD_LONG"}
    ]
    unfunded_buy_candidates.sort(key=lambda row: _safe_float(row.get("opportunity_score"), 0.0), reverse=True)

    reduce_exit_rows = [
        row
        for row in decisions
        if str(row.get("requested_execution_action") or row.get("action_decision") or "").upper() in {"REDUCE_LONG", "EXIT_LONG"}
    ]

    funded_full_rows = [row for row in funded_rows if not bool(row.get("funded_partially"))]
    funded_partial_rows = [row for row in funded_rows if bool(row.get("funded_partially"))]
    unfunded_rows = [row for row in decisions if not bool(row.get("funded")) and str(row.get("planned_execution_action") or "").upper() in {"OPEN_LONG", "ADD_LONG"}]
    priority_band_counts: Counter[str] = Counter(str(item.get("execution_priority_band") or "deferred") for item in decisions)
    partial_reason_counts: Counter[str] = Counter(
        str(item.get("partial_funding_reason") or "none")
        for item in funded_partial_rows
        if str(item.get("partial_funding_reason") or "").strip()
    )
    unfunded_reason_counts: Counter[str] = Counter(str(item.get("funding_decision") or item.get("decision_outcome_code") or "unknown") for item in unfunded_rows)
    partial_capital_total = round(sum(max(_safe_float(item.get("capital_approved_value"), 0.0), 0.0) for item in funded_partial_rows), 4)
    capital_left_unallocated = round(max(remaining_budget, 0.0), 4)
    best_uses = sorted(
        [row for row in funded_rows],
        key=lambda row: (_safe_float(row.get("opportunity_score"), 0.0), -_safe_int(row.get("portfolio_priority_rank"), 0)),
        reverse=True,
    )

    ledger_rows = []
    for row in sorted(decisions, key=lambda item: _safe_int(item.get("portfolio_priority_rank"), 10_000)):
        ledger_rows.append(
            {
                "symbol": row.get("symbol"),
                "portfolio_priority_rank": row.get("portfolio_priority_rank"),
                "planned_execution_action": row.get("planned_execution_action"),
                "requested_execution_action": row.get("requested_execution_action"),
                "funded": bool(row.get("funded")),
                "funded_partially": bool(row.get("funded_partially")),
                "partial_funding_applied": bool(row.get("partial_funding_applied")),
                "funding_status": row.get("funding_status"),
                "funding_decision": row.get("funding_decision"),
                "funding_ratio": row.get("funding_ratio"),
                "partial_funding_reason": row.get("partial_funding_reason"),
                "capital_requested_value": row.get("capital_requested_value"),
                "capital_approved_value": row.get("capital_approved_value"),
                "remaining_unfunded_value": row.get("remaining_unfunded_value"),
                "requested_order_qty": row.get("requested_order_qty"),
                "approved_order_qty": row.get("approved_order_qty"),
                "approved_position_pct": row.get("approved_position_pct"),
                "execution_priority_band": row.get("execution_priority_band"),
                "capital_competition_reason": row.get("capital_competition_reason"),
                "better_use_of_capital_reason": row.get("better_use_of_capital_reason"),
                "replacement_candidate": row.get("replacement_candidate"),
                "displaced_symbol": row.get("displaced_symbol"),
                "decision_outcome_code": row.get("decision_outcome_code"),
                "decision_outcome_detail": row.get("decision_outcome_detail"),
            }
        )

    capital_requested_total = round(sum(max(_safe_float(row.get("capital_requested_value"), 0.0), 0.0) for row in decisions), 4)
    capital_approved_total = round(sum(max(_safe_float(row.get("capital_approved_value"), 0.0), 0.0) for row in decisions), 4)

    summary_payload = {
        "symbols_considered": len(decisions),
        "funded_symbols": [symbol for symbol in funded_symbols if symbol],
        "funded_count": len([s for s in funded_symbols if s]),
        "funded_full_count": len(funded_full_rows),
        "funded_partial_count": len(funded_partial_rows),
        "unfunded_count": len(unfunded_rows),
        "partial_capital_total": partial_capital_total,
        "action_counts": dict(action_counts),
        "top_reason_codes": dict(reason_counts.most_common(12)),
        "top_capital_competition_reasons": dict(competition_reason_counts.most_common(12)),
        "top_partial_funding_reasons": dict(partial_reason_counts.most_common(8)),
        "top_unfunded_reasons": dict(unfunded_reason_counts.most_common(8)),
        "execution_priority_band_counts": dict(priority_band_counts),
        "capital": {
            "portfolio_value": round(portfolio_value, 4),
            "cash_balance": round(cash_balance, 4),
            "reserve_cash": round(reserve_cash, 4),
            "cash_used_for_allocations": round(max(base_allocatable_cash - max(remaining_budget, 0.0), 0.0), 4),
            "cash_remaining": round(max(remaining_budget, 0.0), 4),
            "available_cash_before": round(available_cash_before, 4),
            "available_cash_after": round(remaining_budget + reserve_cash, 4),
            "regime_adjusted_budget": round(regime_adjusted_budget, 4),
            "capital_requested_total": capital_requested_total,
            "capital_approved_total": capital_approved_total,
            "capital_reserved_value": round(reserve_cash, 4),
            "capital_left_unallocated": capital_left_unallocated,
        },
        "highest_unfunded": [
            {
                "symbol": row.get("symbol"),
                "opportunity_score": row.get("opportunity_score"),
                "reason": row.get("decision_outcome_code"),
                "capital_competition_reason": row.get("capital_competition_reason"),
                "better_use_of_capital_reason": row.get("better_use_of_capital_reason"),
                "requested_value": row.get("capital_requested_value"),
            }
            for row in unfunded_buy_candidates[:8]
        ],
        "best_uses_of_capital": [
            {
                "symbol": row.get("symbol"),
                "opportunity_score": row.get("opportunity_score"),
                "funding_decision": row.get("funding_decision"),
                "capital_approved_value": row.get("capital_approved_value"),
                "portfolio_priority_rank": row.get("portfolio_priority_rank"),
            }
            for row in best_uses[:8]
        ],
        "positions_marked_for_reduce_exit": [
            {
                "symbol": row.get("symbol"),
                "action": row.get("requested_execution_action") or row.get("action_decision"),
                "reason": row.get("decision_outcome_code"),
                "detail": row.get("decision_outcome_detail"),
            }
            for row in reduce_exit_rows[:12]
        ],
        "replacement_events": replacement_events,
        "top_partial_funding_reasons": dict(partial_reason_counts.most_common(8)),
        "top_unfunded_reasons": dict(unfunded_reason_counts.most_common(8)),
        "execution_priority_band_counts": dict(priority_band_counts),
        "capital_left_unallocated": capital_left_unallocated,
    }

    ledger_payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "candidates_total": len(decisions),
        "buy_candidates_total": len(buy_candidates),
        "funded_total": len(funded_rows),
        "unfunded_total": len(unfunded_buy_candidates),
        "funded_full_count": len(funded_full_rows),
        "funded_partial_count": len(funded_partial_rows),
        "unfunded_count": len(unfunded_rows),
        "partial_capital_total": partial_capital_total,
        "reduced_total": int(action_counts.get("REDUCE_LONG", 0)),
        "exited_total": int(action_counts.get("EXIT_LONG", 0)),
        "max_new_positions": max_new_positions,
        "portfolio_slot_consumed": max_new_positions - max(slots_remaining, 0),
        "portfolio_slot_available": max(slots_remaining, 0),
        "capital_requested_total": capital_requested_total,
        "capital_approved_total": capital_approved_total,
        "available_cash_before": round(available_cash_before, 4),
        "available_cash_after": round(remaining_budget + reserve_cash, 4),
        "capital_reserved_value": round(reserve_cash, 4),
        "capital_left_unallocated": capital_left_unallocated,
        "regime_adjusted_budget": round(regime_adjusted_budget, 4),
        "cash_reservation_pct": round(reserve_pct, 2),
        "top_capital_competition_reasons": dict(competition_reason_counts.most_common(12)),
        "top_partial_funding_reasons": dict(partial_reason_counts.most_common(8)),
        "top_unfunded_reasons": dict(unfunded_reason_counts.most_common(8)),
        "execution_priority_band_counts": dict(priority_band_counts),
        "rows": ledger_rows,
    }

    return {
        "decisions": decisions,
        "summary": summary_payload,
        "ledger": ledger_payload,
    }


def _classify_sleeve_for_row(row: dict) -> str:
    if _safe_float(row.get("current_position_pct"), 0.0) <= 0.0:
        return "cash"
    if bool(row.get("tactical_small_cap_candidate")):
        return "tactical_aggressive"
    market_cap_bucket = str(row.get("market_cap_bucket") or "").strip().lower()
    volatility_score = _safe_float(row.get("volatility_risk_score"), 50.0)
    liquidity = _safe_float(row.get("liquidity_score"), 50.0)
    setup_type = str(row.get("setup_type") or "").strip().lower()
    if market_cap_bucket in {"mega", "large"} and volatility_score <= 40.0 and liquidity >= 60.0:
        if "dividend" in setup_type or "income" in setup_type:
            return "dividend_income"
        if volatility_score <= 28.0:
            return "defensive_stability"
        return "long_quality"
    if volatility_score <= 32.0:
        return "defensive_stability"
    return "swing_growth"


def build_portfolio_sleeves(
    *,
    decisions: list[dict],
    portfolio_summary: dict | None,
    market_judgment: dict,
) -> dict:
    summary = portfolio_summary if isinstance(portfolio_summary, dict) else {}
    equity = max(_safe_float(summary.get("total_equity") or summary.get("portfolio_value"), 0.0), 0.0)
    cash_balance = max(_safe_float(summary.get("cash_balance"), 0.0), 0.0)
    if equity < 20_000:
        size_tier = "small"
        targets = {
            "tactical_aggressive": 14.0,
            "swing_growth": 34.0,
            "long_quality": 24.0,
            "defensive_stability": 10.0,
            "dividend_income": 4.0,
            "cash": 14.0,
        }
    elif equity <= 100_000:
        size_tier = "medium"
        targets = {
            "tactical_aggressive": 10.0,
            "swing_growth": 28.0,
            "long_quality": 28.0,
            "defensive_stability": 14.0,
            "dividend_income": 8.0,
            "cash": 12.0,
        }
    else:
        size_tier = "large"
        targets = {
            "tactical_aggressive": 5.0,
            "swing_growth": 22.0,
            "long_quality": 31.0,
            "defensive_stability": 18.0,
            "dividend_income": 12.0,
            "cash": 12.0,
        }

    regime_bias = str(market_judgment.get("regime_bias") or "neutral").strip().lower()
    market_quality = _safe_float(market_judgment.get("market_quality_score"), 50.0)
    if regime_bias == "bullish":
        targets["swing_growth"] += 6.0
        targets["tactical_aggressive"] += 4.0
        targets["cash"] -= 6.0
        targets["defensive_stability"] -= 2.0
    elif regime_bias == "defensive":
        targets["cash"] += 8.0
        targets["defensive_stability"] += 6.0
        targets["tactical_aggressive"] -= 5.0
        targets["swing_growth"] -= 5.0
    elif regime_bias == "risk_off":
        targets["cash"] += 14.0
        targets["defensive_stability"] += 8.0
        targets["long_quality"] += 4.0
        targets["tactical_aggressive"] = 0.0
        targets["swing_growth"] -= 10.0
    if market_quality < 48.0:
        targets["cash"] += 6.0
        targets["tactical_aggressive"] = max(targets["tactical_aggressive"] - 3.0, 0.0)
    targets = _normalize_weights(targets)

    actuals = {name: 0.0 for name in _SLEEVE_NAMES}
    for row in decisions or []:
        sleeve = _classify_sleeve_for_row(row)
        actuals[sleeve] += max(_safe_float(row.get("current_position_pct"), 0.0), 0.0)
    if equity > 0.0:
        actuals["cash"] = round((cash_balance / equity) * 100.0, 2)
    actuals = _normalize_weights(actuals)

    rotation_pressure_score = round(
        _clamp(
            _safe_mean([
                _safe_float(row.get("reduce_pressure_score"), 0.0)
                for row in decisions or []
                if str(row.get("requested_execution_action") or row.get("action_decision") or "").upper() in {"REDUCE_LONG", "EXIT_LONG"}
            ], 0.0)
            + len([row for row in decisions or [] if str(row.get("better_use_of_capital_reason") or "").strip()]) * 3.0,
            0.0,
            100.0,
        ),
        4,
    )

    return {
        "portfolio_size_tier": size_tier,
        "sleeve_targets": targets,
        "sleeve_actuals": actuals,
        "sleeve_shift_reason": f"regime={regime_bias} market_quality={market_quality:.1f} size_tier={size_tier}",
        "tactical_aggressive_allowed": bool(market_judgment.get("tactical_small_caps_allowed", False)),
        "dividend_weight_bias": round(targets.get("dividend_income", 0.0), 2),
        "stability_weight_bias": round(targets.get("defensive_stability", 0.0), 2),
        "cash_target_pct": round(targets.get("cash", 0.0), 2),
        "cash_target_reason": "dynamic_regime_and_portfolio_size",
        "rotation_pressure_score": rotation_pressure_score,
    }


def build_self_governed_limits(
    *,
    market_judgment: dict,
    portfolio_sleeves: dict,
    regime: dict,
) -> dict:
    market_quality = _safe_float(market_judgment.get("market_quality_score"), 50.0)
    risk_multiplier = _safe_float(regime.get("risk_multiplier"), 1.0)
    tactical_small_caps_allowed = bool(market_judgment.get("tactical_small_caps_allowed", False))
    premarket_allowed = bool(market_judgment.get("premarket_participation_allowed", False))
    return {
        "max_effective_concentration_pct": round(_clamp(9.0 + market_quality * 0.12 + risk_multiplier * 2.0, 8.0, 24.0), 2),
        "max_small_cap_exposure_pct": round(0.0 if not tactical_small_caps_allowed else _clamp(4.0 + market_quality * 0.08, 4.0, 15.0), 2),
        "max_premarket_exposure_pct": round(0.0 if not premarket_allowed else _clamp(3.0 + market_quality * 0.05, 3.0, 12.0), 2),
        "max_sector_concentration_pct": round(_clamp(14.0 + market_quality * 0.12, 14.0, 28.0), 2),
        "max_open_new_positions_dynamic": max(_safe_int(regime.get("max_new_positions"), 0), 0),
        "cash_target_pct": round(_safe_float(portfolio_sleeves.get("cash_target_pct"), 0.0), 2),
        "catastrophe_only_safety_layer": [
            "runaway_order_storm_guard",
            "duplicate_submission_guard",
            "platform_integrity_guard",
            "execution_loop_breaker",
        ],
    }


def build_judgment_summary(
    *,
    decisions: list[dict],
    market_judgment: dict,
    portfolio_sleeves: dict,
) -> dict:
    sorted_rows = sorted(
        [row for row in decisions or [] if isinstance(row, dict)],
        key=lambda row: _safe_float(row.get("session_adjusted_opportunity_score"), _safe_float(row.get("opportunity_score"), 0.0)),
        reverse=True,
    )
    best_uses = [
        {
            "symbol": row.get("symbol"),
            "action": row.get("requested_execution_action") or row.get("action_decision"),
            "score": row.get("session_adjusted_opportunity_score"),
            "rank": row.get("portfolio_priority_rank"),
            "reason": row.get("decision_outcome_code"),
        }
        for row in sorted_rows[:10]
    ]
    rotations = [
        {
            "rotation_from_symbol": row.get("displaced_symbol") or row.get("symbol"),
            "rotation_to_symbol": row.get("replacement_candidate"),
            "reason": row.get("better_use_of_capital_reason") or row.get("decision_outcome_detail"),
            "score": row.get("session_adjusted_opportunity_score"),
        }
        for row in sorted_rows
        if str(row.get("replacement_candidate") or "").strip() or str(row.get("displaced_symbol") or "").strip()
    ][:8]
    small_caps = [
        {
            "symbol": row.get("symbol"),
            "tactical_small_cap_score": row.get("tactical_small_cap_score"),
            "action": row.get("requested_execution_action") or row.get("action_decision"),
            "reason": row.get("decision_outcome_code"),
        }
        for row in sorted_rows
        if bool(row.get("tactical_small_cap_candidate"))
    ][:8]
    why_not_buying = [
        {
            "symbol": row.get("symbol"),
            "reason": row.get("capital_competition_reason") or row.get("decision_outcome_code"),
            "detail": row.get("better_use_of_capital_reason") or row.get("decision_outcome_detail"),
        }
        for row in sorted_rows
        if not bool(row.get("funded")) and str(row.get("planned_execution_action") or "").upper() in {"OPEN_LONG", "ADD_LONG"}
    ][:8]
    return {
        "market_judgment": market_judgment,
        "portfolio_sleeves": portfolio_sleeves,
        "best_uses_of_capital": best_uses,
        "rotation_opportunities": rotations,
        "why_not_buying": why_not_buying,
        "small_cap_tactical_candidates": small_caps,
    }


def build_review_windows(
    *,
    decisions: list[dict],
    market_judgment: dict,
    portfolio_sleeves: dict,
) -> dict:
    journal = list_trade_journal_entries(limit=200)
    journal_items = journal.get("items") if isinstance(journal, dict) else []
    action_counts = Counter(str(item.get("action_decision") or "HOLD") for item in decisions or [])
    funded_rows = [row for row in decisions or [] if bool(row.get("funded"))]
    reduce_exit_rows = [
        row for row in decisions or []
        if str(row.get("requested_execution_action") or row.get("action_decision") or "").upper() in {"REDUCE_LONG", "EXIT_LONG"}
    ]
    pending_review_count = len([
        row for row in decisions or []
        if str(row.get("requested_execution_action") or row.get("action_decision") or "").upper() in {"OPEN_LONG", "ADD_LONG", "REDUCE_LONG", "EXIT_LONG"}
    ])
    daily_review = {
        "overall_market_posture_quality": round(_safe_float(market_judgment.get("market_quality_score"), 0.0), 4),
        "good_entries": len([row for row in funded_rows if _safe_float(row.get("session_adjusted_opportunity_score"), 0.0) >= 62.0]),
        "good_exits": len([row for row in reduce_exit_rows if _safe_float(row.get("reduce_pressure_score"), 0.0) >= 55.0 or _safe_float(row.get("exit_pressure_score"), 0.0) >= 55.0]),
        "cash_usage_quality": round(_safe_float(portfolio_sleeves.get("cash_target_pct"), 0.0), 4),
        "rotation_quality": len([row for row in decisions or [] if str(row.get("better_use_of_capital_reason") or "").strip()]),
        "small_cap_participation_quality": len([row for row in decisions or [] if bool(row.get("tactical_small_cap_candidate")) and bool(row.get("tactical_small_cap_allowed"))]),
        "news_handling_quality": round(_safe_mean([_safe_float(row.get("news_confidence"), 0.0) for row in decisions or []], 0.0), 4),
        "notes": [
            f"funded={len(funded_rows)}",
            f"pending_trade_reviews={pending_review_count}",
        ],
    }
    weekly_review = {
        "market_fit": str(market_judgment.get("regime_bias") or "neutral"),
        "too_aggressive": bool(_safe_float(portfolio_sleeves.get("rotation_pressure_score"), 0.0) >= 72.0 and _safe_float(portfolio_sleeves.get("cash_target_pct"), 0.0) < 10.0),
        "too_passive": bool(_safe_float(portfolio_sleeves.get("cash_target_pct"), 0.0) >= 28.0 and _safe_int(action_counts.get("OPEN_LONG"), 0) == 0),
        "sleeve_balance_needs_adjustment": bool(abs(_safe_float(portfolio_sleeves.get("sleeve_actuals", {}).get("cash"), 0.0) - _safe_float(portfolio_sleeves.get("cash_target_pct"), 0.0)) >= 8.0),
        "wait_discipline_quality": len([row for row in decisions or [] if bool(row.get("news_requires_wait")) or bool(row.get("engine_conflicts_present"))]),
        "historical_trade_reviews_available": len(journal_items),
        "journal_classification_counts": journal.get("classification_counts") if isinstance(journal, dict) else {},
    }
    return {
        "daily_review": daily_review,
        "weekly_review": weekly_review,
        "trade_review_pending_count": pending_review_count,
        "historical_trade_reviews_available": len(journal_items),
    }



def build_execution_orchestrator_plan(
    *,
    cycle_id: str,
    decisions: list[dict],
    auto_trading_config: dict | None,
    market_open: bool,
) -> dict:
    config = auto_trading_config if isinstance(auto_trading_config, dict) else {}
    orchestrator_enabled = bool(config.get("execution_orchestrator_enabled", True))
    max_submissions = max(_safe_int(config.get("execution_max_submissions_per_cycle"), 6), 1)
    submission_spacing_seconds = max(_safe_int(config.get("execution_submission_spacing_seconds"), 2), 0)
    symbol_cooldown_seconds = max(_safe_int(config.get("execution_symbol_cooldown_seconds"), 90), 0)
    require_release_for_entries = bool(config.get("execution_require_release_before_entries", True))
    retry_enabled = bool(config.get("execution_retry_enabled", True))
    retry_max_attempts = max(_safe_int(config.get("execution_retry_max_attempts"), 2), 1)
    retry_initial_backoff_seconds = max(_safe_int(config.get("execution_retry_initial_backoff_seconds"), 2), 1)
    retry_max_backoff_seconds = max(_safe_int(config.get("execution_retry_max_backoff_seconds"), 20), 1)
    retry_backoff_multiplier = max(_safe_float(config.get("execution_retry_backoff_multiplier"), 2.0), 1.0)
    retry_jitter_enabled = bool(config.get("execution_retry_jitter_enabled", True))
    retry_allowed_for_dependency_wait = bool(config.get("execution_retry_allowed_for_dependency_wait", True))

    timeline: list[dict] = [
        {
            "event": "queue_built",
            "at": datetime.utcnow().isoformat(),
            "detail": "execution queue initialized from portfolio-brain decisions",
            "items_total": len(decisions),
        }
    ]

    queue_items: list[dict] = []
    release_queue_ids: list[str] = []

    for index, row in enumerate(decisions, start=1):
        symbol = str(row.get("symbol") or "").strip().upper()
        action = str(row.get("requested_execution_action") or row.get("action_decision") or "HOLD").strip().upper()
        stage = _derive_execution_stage(row)
        band = str(row.get("execution_priority_band") or "deferred").strip().lower() or "deferred"
        funding_status = str(row.get("funding_status") or "not_applicable").strip().lower() or "not_applicable"
        approved_qty = round(max(_safe_float(row.get("approved_order_qty"), 0.0), 0.0), 4)
        capital_approved = round(max(_safe_float(row.get("capital_approved_value"), 0.0), 0.0), 4)
        capital_requested = round(max(_safe_float(row.get("capital_requested_value"), 0.0), 0.0), 4)
        available_before = max(
            _safe_float(row.get("available_cash_before"), 0.0)
            - _safe_float(row.get("capital_reserved_value"), 0.0),
            0.0,
        )
        requires_capital_release = action in _CAPITAL_DEPLOY_ACTIONS and (
            bool(str(row.get("displaced_symbol") or "").strip())
            or capital_approved > available_before + 1e-6
        )

        session_quality = _normalize_session_quality(
            row.get("session_quality") or ("closed" if not market_open else "normal")
        )
        slippage = str(row.get("estimated_slippage_risk") or "medium").strip().lower() or "medium"
        liquidity_quality = "good"
        if slippage == "high":
            liquidity_quality = "thin"
        elif slippage in {"medium", "elevated"}:
            liquidity_quality = "fair"

        queue_item_id = f"{cycle_id}-q{index:03d}"
        dependency_type = "capital_release_before_entry" if requires_capital_release else "none"

        if action in _CAPITAL_RELEASE_ACTIONS:
            queue_reason = "capital_release_precedes_new_entry"
        elif action in _CAPITAL_DEPLOY_ACTIONS and funding_status == "partially_funded":
            queue_reason = "partial_funding_deferred_after_full_funding"
        elif action in _CAPITAL_DEPLOY_ACTIONS:
            queue_reason = "priority_ranked_capital_deployment"
        else:
            queue_reason = "no_execution_action"

        queue_item = {
            "cycle_id": cycle_id,
            "queue_item_id": queue_item_id,
            "symbol": symbol,
            "requested_execution_action": action if action in _EXECUTION_ACTIONS else None,
            "approved_order_qty": approved_qty,
            "original_approved_order_qty": approved_qty,
            "recomputed_approved_order_qty": approved_qty,
            "capital_requested_value": capital_requested,
            "capital_approved_value": capital_approved,
            "recomputed_capital_approved_value": capital_approved,
            "funding_status": funding_status,
            "execution_priority_band": band,
            "execution_stage": stage,
            "queue_rank": 0,
            "queue_reason": queue_reason,
            "dependency_type": dependency_type,
            "depends_on_queue_item_ids": [],
            "requires_capital_release": bool(requires_capital_release),
            "dependency_satisfied": not bool(requires_capital_release),
            "dependency_outcome": "not_required" if not requires_capital_release else "pending",
            "dependency_expected_release_value": 0.0,
            "dependency_actual_release_value": 0.0,
            "dependency_release_delta": 0.0,
            "dependency_wait_started_at": None,
            "dependency_resolved_at": None,
            "dependency_resolution_reason": None,
            "dependency_final_outcome": "not_required" if not requires_capital_release else "pending",
            "resized_after_capital_release": False,
            "resized_after_execution_result": False,
            "funding_recomputed": False,
            "recompute_reason": None,
            "blocking_reason": None,
            "queue_gate_reason": None,
            "queue_gate_result": "pending",
            "execution_go_no_go": "pending",
            "session_quality": session_quality,
            "estimated_slippage_risk": slippage,
            "liquidity_quality": liquidity_quality,
            "order_style_preference": str(row.get("order_style_preference") or ("market" if band in {"critical", "high"} else "limit")),
            "queue_status": "queued",
            "execution_engine_status": "queued",
            "broker_submission_status": "not_attempted",
            "broker_lifecycle_status": "not_started",
            "execution_final_status": "queued",
            "submitted_to_execution_engine_at": None,
            "broker_submission_attempted_at": None,
            "broker_acknowledged_at": None,
            "broker_last_update_at": None,
            "execution_completed_at": None,
            "first_fill_at": None,
            "final_fill_at": None,
            "retry_eligible": False,
            "retry_reason": None,
            "retry_attempt_count": 0,
            "retry_max_attempts": retry_max_attempts,
            "retry_next_attempt_at": None,
            "backoff_seconds": 0.0,
            "backoff_strategy": "exponential_jitter" if retry_jitter_enabled else "exponential",
            "retry_exhausted": False,
            "backoff_active": False,
            "permanent_failure": False,
            "reconciliation_started_at": None,
            "reconciliation_last_polled_at": None,
            "reconciliation_completed_at": None,
            "reconciliation_poll_count": 0,
            "reconciliation_terminal": False,
            "reconciliation_window_expired": False,
            "reconciliation_stop_reason": None,
            "dependency_release_progress_pct": 0.0,
            "submission_order": None,
            "queue_wait_seconds": None,
            "queue_submitted_at_offset_seconds": None,
        }
        queue_items.append(queue_item)
        if action in _CAPITAL_RELEASE_ACTIONS:
            release_queue_ids.append(queue_item_id)

    if not queue_items:
        return {
            "queue_items": [],
            "summary": {
                "queue_total": 0,
                "submitted_count": 0,
                "deferred_count": 0,
                "skipped_count": 0,
                "waiting_count": 0,
                "ready_count": 0,
                "queue_band_counts": {},
                "queue_reason_counts": {},
                "gating_reason_counts": {},
                "submitted_order_sequence": [],
                "deferred_order_sequence": [],
                "skipped_order_sequence": [],
                "execution_engine_status_counts": {},
                "broker_submission_status_counts": {},
                "broker_lifecycle_status_counts": {},
                "execution_final_status_counts": {},
                "retry_scheduled_count": 0,
                "backoff_active_count": 0,
                "resized_after_execution_result_count": 0,
                "reconciliation_started_count": 0,
                "reconciliation_completed_count": 0,
                "reconciliation_active_count": 0,
                "reconciliation_terminal_count": 0,
                "reconciliation_window_expired_count": 0,
                "reconciliation_poll_count_total": 0,
            },
            "timeline": timeline,
            "dispatch_symbols": [],
        }

    for item in queue_items:
        if item.get("requires_capital_release"):
            item["depends_on_queue_item_ids"] = list(release_queue_ids)
            expected_release = 0.0
            for dep_id in release_queue_ids:
                dep_row = next((entry for entry in queue_items if str(entry.get("queue_item_id")) == str(dep_id)), None)
                expected_release += max(_safe_float((dep_row or {}).get("capital_approved_value"), 0.0), 0.0)
            item["dependency_expected_release_value"] = round(expected_release, 4)

    queue_items.sort(
        key=lambda item: (
            _QUEUE_STAGE_RANK.get(str(item.get("execution_stage") or "observe"), 9),
            _priority_rank(item.get("execution_priority_band")),
            -_safe_float(next((row.get("opportunity_score") for row in decisions if str(row.get("symbol") or "").upper() == str(item.get("symbol") or "").upper()), 0.0), 0.0),
            _safe_int(next((row.get("portfolio_priority_rank") for row in decisions if str(row.get("symbol") or "").upper() == str(item.get("symbol") or "").upper()), 9999), 9999),
            str(item.get("symbol") or ""),
        )
    )

    for rank, item in enumerate(queue_items, start=1):
        item["queue_rank"] = rank

    timeline.append(
        {
            "event": "queue_ranked",
            "at": datetime.utcnow().isoformat(),
            "detail": "queue sorted by stage, priority band, and opportunity rank",
            "items_ranked": len(queue_items),
        }
    )

    status_by_item_id: dict[str, str] = {}
    submitted_count = 0
    schedule_offset = 0
    last_symbol_submit: dict[str, int] = {}
    submitted_sequence: list[dict] = []
    deferred_sequence: list[dict] = []
    skipped_sequence: list[dict] = []

    for item in queue_items:
        action = str(item.get("requested_execution_action") or "").upper()
        symbol = str(item.get("symbol") or "").upper()
        band = str(item.get("execution_priority_band") or "deferred").lower()
        funding_status = str(item.get("funding_status") or "").lower()
        queue_status = "ready"
        gate_reason = None
        dependency_satisfied = True
        dependency_outcome = "not_required"

        if action not in _EXECUTION_ACTIONS:
            queue_status = "skipped"
            gate_reason = "no_action_from_signal"
        elif action in _CAPITAL_DEPLOY_ACTIONS and funding_status not in {"fully_funded", "partially_funded"}:
            queue_status = "skipped"
            gate_reason = "allocator_unfunded"
        elif not market_open:
            queue_status = "deferred"
            gate_reason = "market_closed"
        elif band == "deferred":
            queue_status = "deferred"
            gate_reason = "priority_band_deferred"
        elif action in _CAPITAL_DEPLOY_ACTIONS and _session_rank(item.get("session_quality")) <= 0 and _priority_rank(band) >= 2:
            queue_status = "deferred"
            gate_reason = "session_quality_too_low"
        elif action in _CAPITAL_DEPLOY_ACTIONS and str(item.get("estimated_slippage_risk") or "").lower() == "high" and _priority_rank(band) >= 2:
            queue_status = "deferred"
            gate_reason = "slippage_risk_too_high"
        elif require_release_for_entries and bool(item.get("requires_capital_release")):
            dependency_ids = [str(dep) for dep in (item.get("depends_on_queue_item_ids") or []) if dep]
            unresolved = [dep for dep in dependency_ids if status_by_item_id.get(dep) not in {"submitted", "skipped"}]
            blocked = [dep for dep in dependency_ids if status_by_item_id.get(dep) in {"deferred", "waiting_for_prerequisite", "cancelled"}]
            if unresolved or blocked:
                queue_status = "waiting_for_prerequisite"
                gate_reason = "waiting_for_prior_reduction"
                dependency_satisfied = False
                dependency_outcome = "waiting_for_capital_release"
            else:
                dependency_outcome = "capital_release_preceded_entry"

        if not orchestrator_enabled and action in _EXECUTION_ACTIONS:
            queue_status = "ready"
            gate_reason = None

        if queue_status == "ready":
            if submitted_count >= max_submissions:
                queue_status = "deferred"
                gate_reason = "throttled_due_to_cycle_limit"
            else:
                previous_submit = last_symbol_submit.get(symbol)
                if previous_submit is not None and (schedule_offset - previous_submit) < symbol_cooldown_seconds:
                    queue_status = "deferred"
                    gate_reason = "throttled_due_to_symbol_cooldown"
                else:
                    queue_status = "submitted"
                    submitted_count += 1
                    item["submission_order"] = submitted_count
                    item["queue_wait_seconds"] = schedule_offset
                    item["queue_submitted_at_offset_seconds"] = schedule_offset
                    last_symbol_submit[symbol] = schedule_offset
                    if submission_spacing_seconds > 0:
                        schedule_offset += submission_spacing_seconds
                    submitted_sequence.append(
                        {
                            "queue_item_id": item.get("queue_item_id"),
                            "symbol": symbol,
                            "action": action,
                            "queue_rank": item.get("queue_rank"),
                            "execution_priority_band": band,
                        }
                    )

        item["dependency_satisfied"] = bool(dependency_satisfied)
        item["dependency_outcome"] = dependency_outcome
        item["queue_status"] = queue_status
        item["blocking_reason"] = gate_reason
        item["queue_gate_reason"] = gate_reason
        item["dependency_resolution_reason"] = gate_reason if queue_status in {"waiting_for_prerequisite", "deferred", "skipped"} else "resolved"
        if queue_status == "waiting_for_prerequisite":
            item["dependency_wait_started_at"] = datetime.utcnow().isoformat()
        elif item.get("requires_capital_release"):
            item["dependency_resolved_at"] = datetime.utcnow().isoformat()
            item["dependency_final_outcome"] = "capital_release_completed" if dependency_satisfied else "dependency_pending"
        else:
            item["dependency_final_outcome"] = "not_required"

        if queue_status == "submitted":
            item["queue_gate_result"] = "go"
            item["execution_go_no_go"] = "go"
            item["execution_engine_status"] = "submitted_to_execution_engine"
            item["execution_final_status"] = "submitted_to_execution_engine"
            item["submitted_to_execution_engine_at"] = _iso_offset(
                datetime.utcnow().isoformat(),
                item.get("queue_submitted_at_offset_seconds"),
            )
            timeline.append(
                {
                    "event": "queue_item_ready",
                    "at": datetime.utcnow().isoformat(),
                    "queue_item_id": item.get("queue_item_id"),
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": item.get("queue_rank"),
                }
            )
            timeline.append(
                {
                    "event": "submitted_to_execution_engine",
                    "at": item.get("submitted_to_execution_engine_at") or datetime.utcnow().isoformat(),
                    "queue_item_id": item.get("queue_item_id"),
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": item.get("queue_rank"),
                }
            )
        elif queue_status == "waiting_for_prerequisite":
            item["queue_gate_result"] = "wait"
            item["execution_go_no_go"] = "no_go"
            item["defer_reason"] = gate_reason
            item["execution_engine_status"] = "waiting_for_dependency"
            if retry_enabled and retry_allowed_for_dependency_wait:
                wait_backoff = min(retry_initial_backoff_seconds, retry_max_backoff_seconds)
                item["retry_eligible"] = True
                item["retry_reason"] = gate_reason or "dependency_wait"
                item["retry_attempt_count"] = 0
                item["backoff_seconds"] = float(wait_backoff)
                item["retry_next_attempt_at"] = _iso_offset(datetime.utcnow().isoformat(), wait_backoff)
                item["backoff_active"] = True
                item["execution_final_status"] = "retry_scheduled"
                timeline.append(
                    {
                        "event": "retry_scheduled",
                        "at": datetime.utcnow().isoformat(),
                        "queue_item_id": item.get("queue_item_id"),
                        "symbol": symbol,
                        "action": action,
                        "reason": item.get("retry_reason"),
                        "backoff_seconds": wait_backoff,
                    }
                )
                timeline.append(
                    {
                        "event": "backoff_started",
                        "at": datetime.utcnow().isoformat(),
                        "queue_item_id": item.get("queue_item_id"),
                        "symbol": symbol,
                        "action": action,
                        "backoff_seconds": wait_backoff,
                    }
                )
            else:
                item["execution_final_status"] = "waiting_for_dependency"
            deferred_sequence.append(
                {
                    "queue_item_id": item.get("queue_item_id"),
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": item.get("queue_rank"),
                    "reason": gate_reason,
                }
            )
        elif queue_status == "deferred":
            item["queue_gate_result"] = "defer"
            item["execution_go_no_go"] = "no_go"
            item["defer_reason"] = gate_reason
            item["execution_engine_status"] = "deferred"
            retryable_defer_reasons = {
                "throttled_due_to_cycle_limit",
                "throttled_due_to_symbol_cooldown",
                "waiting_for_cash_refresh",
            }
            if retry_enabled and gate_reason in retryable_defer_reasons:
                defer_backoff = min(
                    retry_max_backoff_seconds,
                    max(
                        retry_initial_backoff_seconds,
                        int(round(retry_initial_backoff_seconds * retry_backoff_multiplier)),
                    ),
                )
                item["retry_eligible"] = True
                item["retry_reason"] = gate_reason
                item["retry_attempt_count"] = 0
                item["backoff_seconds"] = float(defer_backoff)
                item["retry_next_attempt_at"] = _iso_offset(datetime.utcnow().isoformat(), defer_backoff)
                item["backoff_active"] = True
                item["execution_final_status"] = "retry_scheduled"
                timeline.append(
                    {
                        "event": "retry_scheduled",
                        "at": datetime.utcnow().isoformat(),
                        "queue_item_id": item.get("queue_item_id"),
                        "symbol": symbol,
                        "action": action,
                        "reason": gate_reason,
                        "backoff_seconds": defer_backoff,
                    }
                )
            else:
                item["execution_final_status"] = "deferred"
            deferred_sequence.append(
                {
                    "queue_item_id": item.get("queue_item_id"),
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": item.get("queue_rank"),
                    "reason": gate_reason,
                }
            )
        else:
            item["queue_gate_result"] = "skip"
            item["execution_go_no_go"] = "no_go"
            item["defer_reason"] = gate_reason
            item["execution_engine_status"] = "skipped"
            item["execution_final_status"] = "skipped"
            item["execution_completed_at"] = datetime.utcnow().isoformat()
            skipped_sequence.append(
                {
                    "queue_item_id": item.get("queue_item_id"),
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": item.get("queue_rank"),
                    "reason": gate_reason,
                }
            )

        status_by_item_id[str(item.get("queue_item_id") or "")] = queue_status
        timeline.append(
            {
                "event": "queue_item_state",
                "at": datetime.utcnow().isoformat(),
                "queue_item_id": item.get("queue_item_id"),
                "symbol": symbol,
                "action": action,
                "queue_rank": item.get("queue_rank"),
                "queue_status": queue_status,
                "reason": gate_reason,
                "dependency_satisfied": item.get("dependency_satisfied"),
            }
        )

    status_counts = Counter(str(item.get("queue_status") or "unknown") for item in queue_items)
    reason_counts = Counter(str(item.get("queue_reason") or "unknown") for item in queue_items)
    gate_reason_counts = Counter(
        str(item.get("queue_gate_reason") or "none")
        for item in queue_items
        if str(item.get("queue_gate_reason") or "").strip()
    )
    band_counts = Counter(str(item.get("execution_priority_band") or "deferred") for item in queue_items)
    execution_engine_status_counts = Counter(str(item.get("execution_engine_status") or "queued") for item in queue_items)
    broker_submission_status_counts = Counter(str(item.get("broker_submission_status") or "not_attempted") for item in queue_items)
    broker_lifecycle_status_counts = Counter(str(item.get("broker_lifecycle_status") or "not_started") for item in queue_items)
    execution_final_status_counts = Counter(str(item.get("execution_final_status") or "queued") for item in queue_items)

    summary = {
        "queue_total": len(queue_items),
        "submitted_count": int(status_counts.get("submitted", 0)),
        "deferred_count": int(status_counts.get("deferred", 0)),
        "waiting_count": int(status_counts.get("waiting_for_prerequisite", 0)),
        "skipped_count": int(status_counts.get("skipped", 0)),
        "ready_count": int(status_counts.get("ready", 0)),
        "cancelled_count": int(status_counts.get("cancelled", 0)),
        "max_submissions_per_cycle": max_submissions,
        "submission_spacing_seconds": submission_spacing_seconds,
        "symbol_cooldown_seconds": symbol_cooldown_seconds,
        "orchestrator_enabled": bool(orchestrator_enabled),
        "retry_enabled": bool(retry_enabled),
        "retry_max_attempts": retry_max_attempts,
        "retry_initial_backoff_seconds": retry_initial_backoff_seconds,
        "retry_max_backoff_seconds": retry_max_backoff_seconds,
        "retry_backoff_multiplier": round(retry_backoff_multiplier, 4),
        "retry_jitter_enabled": bool(retry_jitter_enabled),
        "queue_band_counts": dict(band_counts),
        "queue_reason_counts": dict(reason_counts.most_common(16)),
        "gating_reason_counts": dict(gate_reason_counts.most_common(16)),
        "execution_engine_status_counts": dict(execution_engine_status_counts.most_common(16)),
        "broker_submission_status_counts": dict(broker_submission_status_counts.most_common(16)),
        "broker_lifecycle_status_counts": dict(broker_lifecycle_status_counts.most_common(16)),
        "execution_final_status_counts": dict(execution_final_status_counts.most_common(16)),
        "retry_scheduled_count": int(execution_final_status_counts.get("retry_scheduled", 0)),
        "backoff_active_count": int(execution_final_status_counts.get("backoff_active", 0)),
        "resized_after_execution_result_count": int(
            sum(1 for item in queue_items if bool(item.get("resized_after_execution_result")))
        ),
        "reconciliation_started_count": int(
            sum(1 for item in queue_items if bool(item.get("reconciliation_started_at")))
        ),
        "reconciliation_completed_count": int(
            sum(1 for item in queue_items if bool(item.get("reconciliation_completed_at")))
        ),
        "reconciliation_active_count": int(
            sum(
                1
                for item in queue_items
                if bool(item.get("reconciliation_started_at")) and not bool(item.get("reconciliation_completed_at"))
            )
        ),
        "reconciliation_terminal_count": int(
            sum(1 for item in queue_items if bool(item.get("reconciliation_terminal")))
        ),
        "reconciliation_window_expired_count": int(
            sum(1 for item in queue_items if bool(item.get("reconciliation_window_expired")))
        ),
        "reconciliation_poll_count_total": int(
            sum(_safe_int(item.get("reconciliation_poll_count"), 0) for item in queue_items)
        ),
        "submitted_order_sequence": submitted_sequence,
        "deferred_order_sequence": deferred_sequence,
        "skipped_order_sequence": skipped_sequence,
    }

    dispatch_symbols = [
        str(item.get("symbol") or "")
        for item in queue_items
        if str(item.get("queue_status") or "") == "submitted" and str(item.get("requested_execution_action") or "") in _EXECUTION_ACTIONS
    ]

    return {
        "queue_items": queue_items,
        "summary": summary,
        "timeline": timeline,
        "dispatch_symbols": dispatch_symbols,
    }


def build_portfolio_brain_payload(
    *,
    cycle_id: str,
    cycle_started_at: str,
    cycle_completed_at: str,
    strategy_mode: str,
    market_open: bool,
    candidate_rows: list[dict],
    held_positions: dict[str, dict],
    portfolio_summary: dict | None,
    auto_trading_config: dict | None,
    session_snapshot: dict | None = None,
) -> dict:
    regime = build_market_regime(
        candidate_rows=candidate_rows,
        market_open=market_open,
        auto_trading_config=auto_trading_config,
    )
    market_judgment = build_market_judgment(
        regime=regime,
        session_snapshot=session_snapshot,
        portfolio_summary=portfolio_summary,
    )
    opportunities = build_opportunity_rows(
        candidate_rows=candidate_rows,
        strategy_mode=strategy_mode,
        regime=regime,
        market_judgment=market_judgment,
    )
    allocation = plan_portfolio_actions(
        opportunities=opportunities,
        held_positions=held_positions,
        portfolio_summary=portfolio_summary,
        auto_trading_config=auto_trading_config,
        regime=regime,
        market_open=market_open,
    )
    decisions = allocation.get("decisions", [])

    execution_orchestrator = build_execution_orchestrator_plan(
        cycle_id=cycle_id,
        decisions=decisions,
        auto_trading_config=auto_trading_config,
        market_open=market_open,
    )
    queue_items = execution_orchestrator.get("queue_items") if isinstance(execution_orchestrator, dict) else []
    if not isinstance(queue_items, list):
        queue_items = []

    queue_by_symbol: dict[str, dict] = {}
    for queue_item in queue_items:
        symbol = str(queue_item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        existing = queue_by_symbol.get(symbol)
        if existing is None or _safe_int(queue_item.get("queue_rank"), 10_000) < _safe_int(existing.get("queue_rank"), 10_000):
            queue_by_symbol[symbol] = queue_item

    for decision in decisions:
        symbol = str(decision.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        queue_item = queue_by_symbol.get(symbol, {})
        if not isinstance(queue_item, dict):
            queue_item = {}
        queue_status = str(queue_item.get("queue_status") or "").strip().lower() or None
        queue_reason = str(queue_item.get("queue_gate_reason") or queue_item.get("blocking_reason") or "").strip().lower() or None
        decision.update(
            {
                "queue_item_id": queue_item.get("queue_item_id"),
                "execution_stage": queue_item.get("execution_stage"),
                "queue_rank": _safe_int(queue_item.get("queue_rank"), 0) or None,
                "queue_reason": queue_item.get("queue_reason"),
                "dependency_type": queue_item.get("dependency_type"),
                "depends_on_queue_item_ids": queue_item.get("depends_on_queue_item_ids") if isinstance(queue_item.get("depends_on_queue_item_ids"), list) else [],
                "requires_capital_release": bool(queue_item.get("requires_capital_release", False)),
                "dependency_satisfied": bool(queue_item.get("dependency_satisfied", False)),
                "dependency_outcome": queue_item.get("dependency_outcome"),
                "resized_after_capital_release": bool(queue_item.get("resized_after_capital_release", False)),
                "funding_recomputed": bool(queue_item.get("funding_recomputed", False)),
                "queue_status": queue_status,
                "queue_gate_result": queue_item.get("queue_gate_result"),
                "queue_gate_reason": queue_reason,
                "blocking_reason": queue_reason,
                "execution_go_no_go": queue_item.get("execution_go_no_go"),
                "defer_reason": queue_item.get("defer_reason"),
                "queue_wait_seconds": queue_item.get("queue_wait_seconds"),
                "submission_order": queue_item.get("submission_order"),
                "queue_submitted_at_offset_seconds": queue_item.get("queue_submitted_at_offset_seconds"),
                "liquidity_quality": queue_item.get("liquidity_quality"),
                "execution_engine_status": queue_item.get("execution_engine_status"),
                "broker_submission_status": queue_item.get("broker_submission_status"),
                "broker_lifecycle_status": queue_item.get("broker_lifecycle_status"),
                "execution_final_status": queue_item.get("execution_final_status"),
                "submitted_to_execution_engine_at": queue_item.get("submitted_to_execution_engine_at"),
                "broker_submission_attempted_at": queue_item.get("broker_submission_attempted_at"),
                "broker_acknowledged_at": queue_item.get("broker_acknowledged_at"),
                "broker_last_update_at": queue_item.get("broker_last_update_at"),
                "execution_completed_at": queue_item.get("execution_completed_at"),
                "retry_eligible": bool(queue_item.get("retry_eligible", False)),
                "retry_reason": queue_item.get("retry_reason"),
                "retry_attempt_count": _safe_int(queue_item.get("retry_attempt_count"), 0),
                "retry_max_attempts": _safe_int(queue_item.get("retry_max_attempts"), 0),
                "retry_next_attempt_at": queue_item.get("retry_next_attempt_at"),
                "backoff_seconds": _safe_float(queue_item.get("backoff_seconds"), 0.0),
                "backoff_strategy": queue_item.get("backoff_strategy"),
                "retry_exhausted": bool(queue_item.get("retry_exhausted", False)),
                "backoff_active": bool(queue_item.get("backoff_active", False)),
                "permanent_failure": bool(queue_item.get("permanent_failure", False)),
                "dependency_expected_release_value": _safe_float(queue_item.get("dependency_expected_release_value"), 0.0),
                "dependency_actual_release_value": _safe_float(queue_item.get("dependency_actual_release_value"), 0.0),
                "dependency_release_delta": _safe_float(queue_item.get("dependency_release_delta"), 0.0),
                "dependency_wait_started_at": queue_item.get("dependency_wait_started_at"),
                "dependency_resolved_at": queue_item.get("dependency_resolved_at"),
                "dependency_resolution_reason": queue_item.get("dependency_resolution_reason"),
                "dependency_final_outcome": queue_item.get("dependency_final_outcome"),
                "resized_after_execution_result": bool(queue_item.get("resized_after_execution_result", False)),
                "original_approved_order_qty": _safe_float(queue_item.get("original_approved_order_qty"), _safe_float(decision.get("approved_order_qty"), 0.0)),
                "recomputed_approved_order_qty": _safe_float(queue_item.get("recomputed_approved_order_qty"), _safe_float(decision.get("approved_order_qty"), 0.0)),
                "recomputed_capital_approved_value": _safe_float(queue_item.get("recomputed_capital_approved_value"), _safe_float(decision.get("capital_approved_value"), 0.0)),
                "recompute_reason": queue_item.get("recompute_reason"),
                "session_quality": queue_item.get("session_quality") or decision.get("session_quality"),
                "estimated_slippage_risk": queue_item.get("estimated_slippage_risk") or decision.get("estimated_slippage_risk"),
                "order_style_preference": queue_item.get("order_style_preference") or decision.get("order_style_preference"),
            }
        )
        if not decision.get("execution_skip_reason") and queue_status in {"deferred", "waiting_for_prerequisite", "skipped"}:
            decision["execution_skip_reason"] = queue_reason

    allocation_summary = allocation.get("summary") if isinstance(allocation.get("summary"), dict) else {}
    allocation_ledger = allocation.get("ledger") if isinstance(allocation.get("ledger"), dict) else {}
    queue_summary = execution_orchestrator.get("summary") if isinstance(execution_orchestrator.get("summary"), dict) else {}
    if allocation_summary is not None:
        allocation_summary["execution_queue_summary"] = queue_summary
    if allocation_ledger is not None:
        allocation_ledger["execution_queue_summary"] = queue_summary

    portfolio_sleeves = build_portfolio_sleeves(
        decisions=decisions,
        portfolio_summary=portfolio_summary,
        market_judgment=market_judgment,
    )
    self_governed_limits = build_self_governed_limits(
        market_judgment=market_judgment,
        portfolio_sleeves=portfolio_sleeves,
        regime=regime,
    )
    judgment_summary = build_judgment_summary(
        decisions=decisions,
        market_judgment=market_judgment,
        portfolio_sleeves=portfolio_sleeves,
    )

    overrides: dict[str, dict] = {}
    for item in decisions:
        symbol = str(item.get("symbol") or "").strip().upper()
        action = str(item.get("requested_execution_action") or "").strip().upper()
        if not symbol:
            continue
        approved_order_qty = _safe_float(item.get("approved_order_qty"), 0.0)
        requested_order_qty = _safe_float(item.get("requested_order_qty"), _safe_float(item.get("proposed_order_qty"), 0.0))
        effective_order_qty = approved_order_qty if approved_order_qty > 0 else _safe_float(item.get("proposed_order_qty"), 0.0)
        priority_band = str(item.get("execution_priority_band") or "deferred").strip().lower() or "deferred"

        overrides[symbol] = {
            "requested_execution_action": action or None,
            "proposed_order_qty": effective_order_qty,
            "requested_order_qty": requested_order_qty,
            "approved_order_qty": approved_order_qty,
            "approved_position_pct": _safe_float(item.get("approved_position_pct"), _safe_float(item.get("current_position_pct"), 0.0)),
            "decision_outcome_code": str(item.get("decision_outcome_code") or "").strip().lower(),
            "decision_outcome_detail": str(item.get("decision_outcome_detail") or "").strip(),
            "target_position_pct": _safe_float(item.get("target_position_pct"), 0.0),
            "current_position_pct": _safe_float(item.get("current_position_pct"), 0.0),
            "desired_delta_pct": _safe_float(item.get("desired_delta_pct"), 0.0),
            "opportunity_score": _safe_float(item.get("opportunity_score"), 0.0),
            "conviction_tier": str(item.get("conviction_tier") or ""),
            "execution_priority_band": priority_band,
            "execution_priority": _legacy_priority_from_band(priority_band),
            "order_style_preference": str(item.get("order_style_preference") or "market"),
            "execution_skip_reason": item.get("execution_skip_reason"),
            "planned_execution_action": item.get("planned_execution_action"),
            "funded": bool(item.get("funded", False)),
            "funded_partially": bool(item.get("funded_partially", False)),
            "partial_funding_applied": bool(item.get("partial_funding_applied", False)),
            "partial_funding_reason": str(item.get("partial_funding_reason") or "").strip() or None,
            "funding_status": str(item.get("funding_status") or "").strip().lower() or None,
            "funding_ratio": _safe_float(item.get("funding_ratio"), 0.0),
            "remaining_unfunded_value": _safe_float(item.get("remaining_unfunded_value"), 0.0),
            "funding_decision": str(item.get("funding_decision") or "").strip().lower() or None,
            "capital_requested_value": _safe_float(item.get("capital_requested_value"), 0.0),
            "capital_approved_value": _safe_float(item.get("capital_approved_value"), 0.0),
            "capital_reserved_value": _safe_float(item.get("capital_reserved_value"), 0.0),
            "available_cash_before": _safe_float(item.get("available_cash_before"), 0.0),
            "available_cash_after": _safe_float(item.get("available_cash_after"), 0.0),
            "regime_adjusted_budget": _safe_float(item.get("regime_adjusted_budget"), 0.0),
            "capital_competition_reason": str(item.get("capital_competition_reason") or "").strip() or None,
            "better_use_of_capital_reason": str(item.get("better_use_of_capital_reason") or "").strip() or None,
            "replacement_candidate": str(item.get("replacement_candidate") or "").strip() or None,
            "displaced_symbol": str(item.get("displaced_symbol") or "").strip() or None,
            "portfolio_slot_consumed": _safe_int(item.get("portfolio_slot_consumed"), 0),
            "portfolio_slot_available": _safe_int(item.get("portfolio_slot_available"), 0),
            "queue_item_id": item.get("queue_item_id"),
            "execution_stage": item.get("execution_stage"),
            "queue_rank": _safe_int(item.get("queue_rank"), 0) or None,
            "queue_reason": item.get("queue_reason"),
            "dependency_type": item.get("dependency_type"),
            "depends_on_queue_item_ids": item.get("depends_on_queue_item_ids") if isinstance(item.get("depends_on_queue_item_ids"), list) else [],
            "requires_capital_release": bool(item.get("requires_capital_release", False)),
            "dependency_satisfied": bool(item.get("dependency_satisfied", False)),
            "dependency_outcome": item.get("dependency_outcome"),
            "resized_after_capital_release": bool(item.get("resized_after_capital_release", False)),
            "funding_recomputed": bool(item.get("funding_recomputed", False)),
            "queue_status": item.get("queue_status"),
            "queue_gate_result": item.get("queue_gate_result"),
            "queue_gate_reason": item.get("queue_gate_reason"),
            "blocking_reason": item.get("blocking_reason"),
            "execution_go_no_go": item.get("execution_go_no_go"),
            "defer_reason": item.get("defer_reason"),
            "queue_wait_seconds": item.get("queue_wait_seconds"),
            "submission_order": item.get("submission_order"),
            "queue_submitted_at_offset_seconds": item.get("queue_submitted_at_offset_seconds"),
            "liquidity_quality": item.get("liquidity_quality"),
            "execution_engine_status": item.get("execution_engine_status"),
            "broker_submission_status": item.get("broker_submission_status"),
            "broker_lifecycle_status": item.get("broker_lifecycle_status"),
            "execution_final_status": item.get("execution_final_status"),
            "submitted_to_execution_engine_at": item.get("submitted_to_execution_engine_at"),
            "broker_submission_attempted_at": item.get("broker_submission_attempted_at"),
            "broker_acknowledged_at": item.get("broker_acknowledged_at"),
            "broker_last_update_at": item.get("broker_last_update_at"),
            "execution_completed_at": item.get("execution_completed_at"),
            "retry_eligible": bool(item.get("retry_eligible", False)),
            "retry_reason": item.get("retry_reason"),
            "retry_attempt_count": _safe_int(item.get("retry_attempt_count"), 0),
            "retry_max_attempts": _safe_int(item.get("retry_max_attempts"), 0),
            "retry_next_attempt_at": item.get("retry_next_attempt_at"),
            "backoff_seconds": _safe_float(item.get("backoff_seconds"), 0.0),
            "backoff_strategy": item.get("backoff_strategy"),
            "retry_exhausted": bool(item.get("retry_exhausted", False)),
            "backoff_active": bool(item.get("backoff_active", False)),
            "permanent_failure": bool(item.get("permanent_failure", False)),
            "dependency_expected_release_value": _safe_float(item.get("dependency_expected_release_value"), 0.0),
            "dependency_actual_release_value": _safe_float(item.get("dependency_actual_release_value"), 0.0),
            "dependency_release_delta": _safe_float(item.get("dependency_release_delta"), 0.0),
            "dependency_wait_started_at": item.get("dependency_wait_started_at"),
            "dependency_resolved_at": item.get("dependency_resolved_at"),
            "dependency_resolution_reason": item.get("dependency_resolution_reason"),
            "dependency_final_outcome": item.get("dependency_final_outcome"),
            "resized_after_execution_result": bool(item.get("resized_after_execution_result", False)),
            "original_approved_order_qty": _safe_float(item.get("original_approved_order_qty"), approved_order_qty),
            "recomputed_approved_order_qty": _safe_float(item.get("recomputed_approved_order_qty"), approved_order_qty),
            "recomputed_capital_approved_value": _safe_float(item.get("recomputed_capital_approved_value"), _safe_float(item.get("capital_approved_value"), 0.0)),
            "recompute_reason": item.get("recompute_reason"),
        }

    review_action_counts = Counter(str(item.get("action_decision") or "HOLD") for item in decisions)
    review_reason_counts = Counter(str(item.get("decision_outcome_code") or "unknown") for item in decisions)
    top_blockers = [
        {"reason_code": code, "count": count}
        for code, count in review_reason_counts.most_common(8)
        if code not in {"open_long_allowed", "add_long_allowed", "hold_position_valid"}
    ]
    review_windows = build_review_windows(
        decisions=decisions,
        market_judgment=market_judgment,
        portfolio_sleeves=portfolio_sleeves,
    )

    self_review = {
        "cycle_id": cycle_id,
        "generated_at": datetime.utcnow().isoformat(),
        "regime": {
            "code": regime.get("regime_code"),
            "bias": regime.get("regime_bias"),
            "confidence": regime.get("regime_confidence"),
        },
        "actions_taken": dict(review_action_counts),
        "top_blockers": top_blockers,
        "capital_usage": allocation.get("summary", {}).get("capital", {}),
        "strongest_ideas_not_funded": allocation.get("summary", {}).get("highest_unfunded", []),
        "best_uses_of_capital": allocation.get("summary", {}).get("best_uses_of_capital", []),
        "positions_marked_for_reduce_exit": allocation.get("summary", {}).get("positions_marked_for_reduce_exit", []),
        "top_capital_competition_reasons": allocation.get("summary", {}).get("top_capital_competition_reasons", {}),
        "replacement_events": allocation.get("summary", {}).get("replacement_events", []),
        "execution_queue_summary": queue_summary,
        "execution_timeline_preview": (execution_orchestrator.get("timeline")[:20] if isinstance(execution_orchestrator, dict) and isinstance(execution_orchestrator.get("timeline"), list) else []),
        "daily_review": review_windows.get("daily_review", {}),
        "weekly_review": review_windows.get("weekly_review", {}),
        "trade_review_pending_count": review_windows.get("trade_review_pending_count"),
        "historical_trade_reviews_available": review_windows.get("historical_trade_reviews_available"),
    }

    return {
        "cycle_id": cycle_id,
        "cycle_started_at": cycle_started_at,
        "cycle_completed_at": cycle_completed_at,
        "strategy_mode": strategy_mode,
        "market_open": bool(market_open),
        "generated_at": datetime.utcnow().isoformat(),
        "regime": regime,
        "market_judgment": market_judgment,
        "portfolio_sleeves": portfolio_sleeves,
        "self_governed_limits": self_governed_limits,
        "judgment_summary": judgment_summary,
        "opportunities": opportunities,
        "allocation": {
            **allocation,
            "decision_overrides": overrides,
            "execution_queue": execution_orchestrator.get("queue_items") if isinstance(execution_orchestrator, dict) else [],
            "execution_timeline": execution_orchestrator.get("timeline") if isinstance(execution_orchestrator, dict) else [],
            "execution_queue_summary": execution_orchestrator.get("summary") if isinstance(execution_orchestrator, dict) else {},
            "dispatch_symbols": execution_orchestrator.get("dispatch_symbols") if isinstance(execution_orchestrator, dict) else [],
        },
        "execution_orchestrator": execution_orchestrator if isinstance(execution_orchestrator, dict) else {},
        "self_review": self_review,
    }
