import os
from pathlib import Path
from functools import lru_cache

import pandas as pd


BEST_SETUP_FILE = Path(__file__).resolve().parent / "leaders_optimizer_best.csv"
SEED_BEST_SETUP_FILE = Path(__file__).resolve().parent / "seed_data" / "leaders_optimizer_best.seed.csv"


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _clamp(value, low, high):
    return max(low, min(high, value))


def _signal_bias(result):
    signal = str(result.get("enhanced_signal", result.get("signal", "HOLD"))).upper()
    if signal == "BUY":
        return 1
    if signal == "SELL":
        return -1
    return 0


@lru_cache(maxsize=1)
def _load_best_setup_map():
    configured_path = str(os.getenv("MARKET_AI_BEST_SETUP_FILE", "") or "").strip()
    candidate_paths = []
    if configured_path:
        candidate_paths.append(Path(configured_path))
    candidate_paths.extend([BEST_SETUP_FILE, SEED_BEST_SETUP_FILE])

    df = None
    for candidate in candidate_paths:
        if not candidate.exists():
            continue
        try:
            df = pd.read_csv(candidate)
            break
        except Exception:
            continue

    if df is None:
        return {}

    if df.empty or "instrument" not in df.columns:
        return {}

    best_map = {}
    for _, row in df.iterrows():
        symbol = str(row.get("instrument", "")).strip().upper()
        if not symbol:
            continue

        best_map[symbol] = {
            "hold_days": _safe_int(row.get("hold_days"), 0),
            "buy_score_threshold": _safe_int(row.get("buy_score_threshold"), 0),
            "sell_score_threshold": _safe_int(row.get("sell_score_threshold"), 0),
            "overall_win_rate_pct": _safe_float(row.get("overall_win_rate_pct"), 0.0),
            "avg_trade_return_pct": _safe_float(row.get("avg_trade_return_pct"), 0.0),
            "stability_score": _safe_float(row.get("stability_score"), 0.0),
        }

    return best_map


def _format_best_setup(best_setup_values):
    if not best_setup_values:
        return ""

    hold_days = _safe_int(best_setup_values.get("hold_days"), 0)
    buy_threshold = _safe_int(best_setup_values.get("buy_score_threshold"), 0)
    sell_threshold = _safe_int(best_setup_values.get("sell_score_threshold"), 0)

    if hold_days <= 0:
        return ""

    return f"H{hold_days} / B{buy_threshold} / S{sell_threshold}"


def _setup_type_label(result):
    signal = str(result.get("enhanced_signal", result.get("signal", "HOLD"))).upper()
    candle = str(result.get("candle_signal", "NONE")).upper()
    squeeze_ready = bool(result.get("squeeze_ready", False))
    mtf_score = _safe_int(result.get("mtf_score", 0))
    rs_score = _safe_int(result.get("rs_score", 0))
    trend_quality_score = _safe_int(result.get("trend_quality_score", 0))

    bullish_candle = candle in ["HAMMER", "BULLISH_ENGULFING"]
    bearish_candle = candle in ["SHOOTING_STAR", "BEARISH_ENGULFING"]

    if signal == "BUY":
        if squeeze_ready and mtf_score > 0:
            return "Breakout Ready"
        if bullish_candle and trend_quality_score >= 0:
            return "Bullish Reversal"
        if mtf_score > 0 and rs_score > 0 and trend_quality_score >= 1:
            return "Trend Continuation"
        if rs_score > 0:
            return "Relative Strength Long"
        return "Long Watch"

    if signal == "SELL":
        if bearish_candle and trend_quality_score <= 0:
            return "Bearish Reversal"
        if mtf_score < 0 and rs_score < 0 and trend_quality_score <= -1:
            return "Trend Breakdown"
        if rs_score < 0:
            return "Relative Weakness Short"
        return "Short Watch"

    if squeeze_ready:
        return "Compression Watch"
    return "Neutral Watch"


def _confidence_score(result):
    signal_bias = _signal_bias(result)
    enhanced_score = _safe_float(result.get("enhanced_combined_score", result.get("combined_score", 0)))
    technical_score = _safe_float(result.get("technical_score", 0))
    mtf_score = _safe_float(result.get("mtf_score", 0))
    rs_score = _safe_float(result.get("rs_score", 0))
    trend_quality_score = _safe_float(result.get("trend_quality_score", 0))
    ml_confidence = _safe_float(result.get("ml_confidence", 0.5))
    candle = str(result.get("candle_signal", "NONE")).upper()
    squeeze_ready = bool(result.get("squeeze_ready", False))

    directional_score = 50.0
    directional_score += abs(enhanced_score) * 6.0
    directional_score += abs(technical_score) * 4.0
    directional_score += abs(mtf_score) * 5.0
    directional_score += abs(rs_score) * 4.0
    directional_score += min(abs(trend_quality_score), 3.0) * 3.0

    if signal_bias > 0 and candle in ["HAMMER", "BULLISH_ENGULFING"]:
        directional_score += 5.0
    elif signal_bias < 0 and candle in ["SHOOTING_STAR", "BEARISH_ENGULFING"]:
        directional_score += 5.0
    elif candle == "DOJI":
        directional_score -= 3.0

    if squeeze_ready and signal_bias != 0:
        directional_score += 3.0

    if result.get("ml_confidence") is not None:
        directional_score += _clamp((ml_confidence - 0.5) * 20.0, -5.0, 10.0)

    if signal_bias == 0:
        directional_score -= 10.0

    return int(round(_clamp(directional_score, 0.0, 99.0)))


def _rank_score(result):
    confidence = _confidence_score(result)
    enhanced_score = _safe_float(result.get("enhanced_combined_score", result.get("combined_score", 0)))
    technical_score = _safe_float(result.get("technical_score", 0))
    mtf_score = _safe_float(result.get("mtf_score", 0))
    rs_score = _safe_float(result.get("rs_score", 0))
    trend_quality_score = _safe_float(result.get("trend_quality_score", 0))
    best_setup_values = result.get("best_setup_values") or {}

    score = confidence
    score += enhanced_score * 8.0
    score += technical_score * 2.5
    score += mtf_score * 3.0
    score += rs_score * 3.0
    score += trend_quality_score * 1.5
    score += _safe_float(best_setup_values.get("stability_score"), 0.0) * 0.15
    score += _safe_float(best_setup_values.get("avg_trade_return_pct"), 0.0) * 2.0
    score += _safe_float(best_setup_values.get("overall_win_rate_pct"), 0.0) * 0.1
    return round(score, 4)


def rank_analysis_result(result):
    if not isinstance(result, dict):
        return {
            "rank": "",
            "confidence": "",
            "best_setup": "",
            "setup_type": "",
            "best_setup_values": {},
            "rank_score": -9999,
        }

    ranked = dict(result)
    symbol = str(ranked.get("instrument", "")).strip().upper()
    best_setup_values = _load_best_setup_map().get(symbol, {})

    ranked["best_setup_values"] = best_setup_values
    ranked["best_setup"] = _format_best_setup(best_setup_values)
    ranked["setup_type"] = _setup_type_label(result)
    ranked["confidence"] = _confidence_score(ranked)
    ranked["rank_score"] = _rank_score(ranked)
    ranked.setdefault("rank", "")
    return ranked


def build_ranked_scan_rows(results):
    ranked_rows = []
    error_rows = []

    for result in results:
        signal = str(result.get("enhanced_signal", result.get("signal", ""))).upper()
        if signal == "ERROR" or result.get("error"):
            row = dict(result)
            row["rank"] = ""
            row["confidence"] = ""
            row["best_setup"] = row.get("best_setup", "")
            row["setup_type"] = row.get("setup_type", "")
            row["best_setup_values"] = row.get("best_setup_values", {})
            row["rank_score"] = -9999
            error_rows.append(row)
            continue

        ranked_rows.append(rank_analysis_result(result))

    ranked_rows.sort(
        key=lambda row: (
            _safe_float(row.get("rank_score", -9999)),
            _safe_float(row.get("enhanced_combined_score", row.get("combined_score", -9999))),
            _safe_float((row.get("best_setup_values") or {}).get("stability_score"), 0.0),
            _safe_float(row.get("ml_confidence", 0)),
            str(row.get("instrument", "")),
        ),
        reverse=True,
    )

    for idx, row in enumerate(ranked_rows, start=1):
        row["rank"] = idx

    return ranked_rows + error_rows


def summarize_top_candidates(rows, limit=3):
    clean_rows = [row for row in rows if str(row.get("signal", "")).upper() != "ERROR"]
    lines = []

    for row in clean_rows[:limit]:
        setup = row.get("best_setup") or row.get("setup_type") or "-"
        lines.append(
            f"#{row.get('rank', '-')} {row.get('instrument', '-')} | "
            f"{row.get('signal', '-')} | conf {row.get('confidence', '-')} | "
            f"{setup} | score {row.get('combined_score', '-')}"
        )

    return lines


def summarize_top_candidates_by_signal(rows, signal, limit=3):
    target_signal = str(signal).upper().strip()
    filtered_rows = [
        row for row in rows
        if str(row.get("signal", "")).upper() == target_signal
    ]
    lines = []

    for row in filtered_rows[:limit]:
        setup = row.get("best_setup") or row.get("setup_type") or "-"
        lines.append(
            f"#{row.get('rank', '-')} {row.get('instrument', '-')} | "
            f"conf {row.get('confidence', '-')} | "
            f"{setup} | score {row.get('combined_score', '-')}"
        )

    return lines
