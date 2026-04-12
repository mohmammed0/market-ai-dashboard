import pandas as pd

from technical_engine import calculate_technical_indicators
from ai_news_engine import fetch_ai_news
from app_logger import get_logger
from core.source_data import load_symbol_source_data

try:
    from ml_engine import predict_latest as predict_ml_latest
except Exception:
    predict_ml_latest = None

logger = get_logger("analysis_engine")


def _safe_round(value, digits=4):
    if pd.isna(value):
        return None
    return round(float(value), digits)


def _fallback_news_payload(error_message=None):
    return {
        "news_score": 0,
        "news_sentiment": "NEUTRAL",
        "ai_enabled": False,
        "ai_summary": "",
        "ai_news_score": 0,
        "ai_news_sentiment": "NEUTRAL",
        "ai_error": error_message or "News unavailable; returned analysis without external news.",
        "articles_count": 0,
        "positive_count": 0,
        "negative_count": 0,
        "neutral_count": 0,
        "news_items": [],
    }


def _combined_signal(score):
    if score >= 3:
        return "BUY"
    if score <= -3:
        return "SELL"
    return "HOLD"


def _ml_score_from_result(ml_result):
    if not isinstance(ml_result, dict):
        return 0

    if ml_result.get("error"):
        return 0

    ml_signal = str(ml_result.get("ml_signal", "HOLD")).upper()
    ml_confidence = ml_result.get("ml_confidence")

    try:
        ml_confidence = float(ml_confidence)
    except Exception:
        return 0

    if ml_confidence < 0.55:
        return 0

    if ml_signal == "BUY":
        return 1
    if ml_signal == "SELL":
        return -1
    return 0


def _timeframe_direction(tf):
    if not isinstance(tf, dict):
        return 0

    signal = str(tf.get("signal", "HOLD")).upper()
    regime = str(tf.get("market_regime", "NEUTRAL")).upper()
    trend = str(tf.get("trend_mode", "RANGE")).upper()

    try:
        technical_score = int(tf.get("technical_score", 0))
    except Exception:
        technical_score = 0

    bullish = 0
    bearish = 0

    if signal == "BUY" or technical_score >= 3:
        bullish += 1
    elif signal == "SELL" or technical_score <= -3:
        bearish += 1

    if regime == "BULLISH":
        bullish += 1
    elif regime == "BEARISH":
        bearish += 1

    if trend in ["STRONG_UPTREND", "UPTREND"]:
        bullish += 1
    elif trend in ["STRONG_DOWNTREND", "DOWNTREND"]:
        bearish += 1

    if bullish >= 2 and bullish > bearish:
        return 1
    if bearish >= 2 and bearish > bullish:
        return -1
    return 0


def _mtf_score_from_map(multi_timeframe):
    daily_dir = _timeframe_direction(multi_timeframe.get("daily", {}))
    weekly_dir = _timeframe_direction(multi_timeframe.get("weekly", {}))
    monthly_dir = _timeframe_direction(multi_timeframe.get("monthly", {}))

    mtf_score = 0

    if weekly_dir != 0 and weekly_dir == monthly_dir:
        mtf_score += weekly_dir
        if daily_dir == weekly_dir:
            mtf_score += weekly_dir
    elif daily_dir != 0 and weekly_dir != 0 and daily_dir == weekly_dir:
        mtf_score += daily_dir

    if mtf_score > 2:
        mtf_score = 2
    if mtf_score < -2:
        mtf_score = -2

    dir_map = {1: "BULLISH", -1: "BEARISH", 0: "NEUTRAL"}
    return {
        "mtf_score": mtf_score,
        "mtf_alignment": (
            f"Daily={dir_map[daily_dir]} | "
            f"Weekly={dir_map[weekly_dir]} | "
            f"Monthly={dir_map[monthly_dir]}"
        )
    }


def _detect_market_regime(row):
    close_price = row.get("close")
    ma20 = row.get("ma20")
    ma50 = row.get("ma50")
    adx14 = row.get("adx14")
    bb_width = row.get("bb_width")
    volatility20 = row.get("volatility20")

    regime = "NEUTRAL"
    trend_mode = "RANGE"
    regime_score = 0

    try:
        close_price = float(close_price) if pd.notna(close_price) else None
        ma20 = float(ma20) if pd.notna(ma20) else None
        ma50 = float(ma50) if pd.notna(ma50) else None
        adx14 = float(adx14) if pd.notna(adx14) else None
        bb_width = float(bb_width) if pd.notna(bb_width) else None
        volatility20 = float(volatility20) if pd.notna(volatility20) else None
    except Exception:
        return {
            "market_regime": regime,
            "trend_mode": trend_mode,
            "regime_score": regime_score,
        }

    if close_price is not None and ma20 is not None and ma50 is not None:
        if close_price > ma20 > ma50:
            regime = "BULLISH"
            regime_score = 1
        elif close_price < ma20 < ma50:
            regime = "BEARISH"
            regime_score = -1

    if adx14 is not None:
        if adx14 >= 25:
            if regime == "BULLISH":
                trend_mode = "STRONG_UPTREND"
                regime_score = 2
            elif regime == "BEARISH":
                trend_mode = "STRONG_DOWNTREND"
                regime_score = -2
            else:
                trend_mode = "TRENDING"
        elif adx14 >= 20:
            if regime == "BULLISH":
                trend_mode = "UPTREND"
            elif regime == "BEARISH":
                trend_mode = "DOWNTREND"

    if bb_width is not None and bb_width < 0.05:
        trend_mode = "COMPRESSION"

    if volatility20 is not None and volatility20 > 0.35 and trend_mode == "RANGE":
        trend_mode = "HIGH_VOLATILITY"

    return {
        "market_regime": regime,
        "trend_mode": trend_mode,
        "regime_score": regime_score,
    }


def _empty_timeframe_snapshot(label, rule):
    return {
        "label": label,
        "timeframe_rule": rule,
        "bars": 0,
        "signal": "HOLD",
        "technical_score": 0,
        "close": None,
        "rsi14": None,
        "adx14": None,
        "market_regime": "NEUTRAL",
        "trend_mode": "RANGE",
        "date": None,
    }


def _resample_ohlcv(raw_df, rule):
    if raw_df is None or raw_df.empty or "datetime" not in raw_df.columns:
        return pd.DataFrame()

    tf_df = raw_df.copy()
    tf_df["datetime"] = pd.to_datetime(tf_df["datetime"])
    tf_df = tf_df.sort_values("datetime").set_index("datetime")

    agg_map = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }

    if "volume" in tf_df.columns:
        agg_map["volume"] = "sum"

    tf_df = tf_df.resample(rule).agg(agg_map)
    tf_df = tf_df.dropna(subset=["open", "high", "low", "close"]).reset_index()

    if "volume" not in tf_df.columns:
        tf_df["volume"] = 0

    return tf_df


def _build_timeframe_snapshot(raw_df, rule, label):
    if raw_df is None or raw_df.empty:
        return _empty_timeframe_snapshot(label, rule)

    if str(rule).upper() == "D":
        tf_df = raw_df.copy()
        tf_df["datetime"] = pd.to_datetime(tf_df["datetime"])
        tf_df = tf_df.sort_values("datetime").reset_index(drop=True)
    else:
        tf_df = _resample_ohlcv(raw_df, rule)

    if tf_df.empty:
        return _empty_timeframe_snapshot(label, rule)

    tf_df = calculate_technical_indicators(tf_df)

    clean_tf_df = tf_df.dropna(
        subset=[
            "ma20", "ma50", "rsi14", "macd", "macd_signal",
            "macd_hist", "bb_upper", "bb_lower", "atr14", "volume_ratio"
        ]
    ).copy()

    if clean_tf_df.empty:
        row = tf_df.iloc[-1]
        return {
            "label": label,
            "timeframe_rule": rule,
            "bars": int(len(tf_df)),
            "signal": "HOLD",
            "technical_score": 0,
            "close": _safe_round(row.get("close")),
            "rsi14": _safe_round(row.get("rsi14")),
            "adx14": _safe_round(row.get("adx14")),
            "market_regime": "NEUTRAL",
            "trend_mode": "RANGE",
            "date": str(row.get("datetime"))[:10] if pd.notna(row.get("datetime")) else None,
        }

    row = clean_tf_df.iloc[-1]
    regime = _detect_market_regime(row)

    return {
        "label": label,
        "timeframe_rule": rule,
        "bars": int(len(clean_tf_df)),
        "signal": str(row.get("final_signal", "HOLD")),
        "technical_score": int(row.get("technical_score", 0)) if pd.notna(row.get("technical_score")) else 0,
        "close": _safe_round(row.get("close")),
        "rsi14": _safe_round(row.get("rsi14")),
        "adx14": _safe_round(row.get("adx14")),
        "market_regime": regime.get("market_regime"),
        "trend_mode": regime.get("trend_mode"),
        "date": str(row.get("datetime"))[:10] if pd.notna(row.get("datetime")) else None,
    }


def _build_trade_plan(row, final_signal):
    close_price = _safe_round(row.get("close"))
    atr14 = _safe_round(row.get("atr14"))
    support = _safe_round(row.get("breakout_low_20"))
    resistance = _safe_round(row.get("breakout_high_20"))

    atr_stop = None
    atr_target = None
    risk_reward = None

    if close_price is not None and atr14 is not None:
        if final_signal == "BUY":
            atr_stop = _safe_round(close_price - (atr14 * 1.5))
            atr_target = _safe_round(close_price + (atr14 * 3.0))
        elif final_signal == "SELL":
            atr_stop = _safe_round(close_price + (atr14 * 1.5))
            atr_target = _safe_round(close_price - (atr14 * 3.0))
        else:
            atr_stop = _safe_round(close_price - (atr14 * 1.5))
            atr_target = _safe_round(close_price + (atr14 * 1.5))

    if close_price is not None and atr_stop is not None and atr_target is not None:
        try:
            risk = abs(close_price - atr_stop)
            reward = abs(atr_target - close_price)
            if risk and risk > 0:
                risk_reward = _safe_round(reward / risk, 2)
        except Exception:
            risk_reward = None

    return {
        "support": support,
        "resistance": resistance,
        "atr_stop": atr_stop,
        "atr_target": atr_target,
        "risk_reward": risk_reward,
    }


def _load_source_data(instrument, start_time, end_time):
    result = load_symbol_source_data(instrument, start_date=start_time, end_date=end_time, persist_on_fetch=True)
    if result.error:
        return None, result.error
    if result.frame is None or result.frame.empty:
        return None, f"No data found for {instrument} from {start_time} to {end_time}"

    df = result.frame.rename(columns={"date": "datetime"}).copy()
    return df[["datetime", "instrument", "open", "high", "low", "close", "volume"]].copy(), None


def _build_relative_strength_snapshot(raw_df, start_time, end_time, benchmark="SPY"):
    default_snapshot = {
        "rs_benchmark": benchmark,
        "rs_spy_20": None,
        "rs_spy_63": None,
        "rs_state": "NEUTRAL",
        "rs_score": 0,
    }

    if raw_df is None or raw_df.empty:
        return default_snapshot

    try:
        instrument_name = str(raw_df["instrument"].iloc[0]).upper()
    except Exception:
        instrument_name = ""

    if instrument_name == benchmark.upper():
        default_snapshot["rs_spy_20"] = 0.0
        default_snapshot["rs_spy_63"] = 0.0
        default_snapshot["rs_state"] = "BENCHMARK"
        return default_snapshot

    bench_df, bench_error = _load_source_data(benchmark, start_time, end_time)
    if bench_error or bench_df is None or bench_df.empty:
        return default_snapshot

    left = raw_df[["datetime", "close"]].copy()
    right = bench_df[["datetime", "close"]].copy().rename(columns={"close": "benchmark_close"})

    left["datetime"] = pd.to_datetime(left["datetime"])
    right["datetime"] = pd.to_datetime(right["datetime"])

    merged = left.merge(right, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    if merged.empty:
        return default_snapshot

    merged["asset_ret_20"] = merged["close"].pct_change(20)
    merged["bench_ret_20"] = merged["benchmark_close"].pct_change(20)
    merged["asset_ret_63"] = merged["close"].pct_change(63)
    merged["bench_ret_63"] = merged["benchmark_close"].pct_change(63)

    merged["rs_spy_20"] = (merged["asset_ret_20"] - merged["bench_ret_20"]) * 100
    merged["rs_spy_63"] = (merged["asset_ret_63"] - merged["bench_ret_63"]) * 100

    row = merged.iloc[-1]
    rs20 = _safe_round(row.get("rs_spy_20"))
    rs63 = _safe_round(row.get("rs_spy_63"))

    rs_state = "NEUTRAL"
    rs_score = 0

    try:
        rs20_num = float(rs20) if rs20 is not None else None
        rs63_num = float(rs63) if rs63 is not None else None
    except Exception:
        rs20_num = None
        rs63_num = None

    if rs63_num is not None and rs20_num is not None:
        if rs63_num >= 5 and rs20_num >= 0:
            rs_state = "OUTPERFORM"
            rs_score = 1
        elif rs63_num <= -5 and rs20_num <= 0:
            rs_state = "UNDERPERFORM"
            rs_score = -1

    return {
        "rs_benchmark": benchmark,
        "rs_spy_20": rs20,
        "rs_spy_63": rs63,
        "rs_state": rs_state,
        "rs_score": rs_score,
    }


def get_latest_signal(instrument="AAPL", start_time="2024-01-01", end_time="2026-04-02"):
    instrument = instrument.upper().strip()
    logger.info(f"run_analysis started | instrument={instrument} | start={start_time} | end={end_time}")

    df, load_error = _load_source_data(instrument, start_time, end_time)
    if load_error:
        logger.warning(load_error)
        return {"error": load_error}

    if df is None or df.empty:
        logger.warning(f"No raw data found | instrument={instrument} | start={start_time} | end={end_time}")
        return {
            "error": f"No data found for {instrument} from {start_time} to {end_time}"
        }

    raw_df = df.copy()
    rs_snapshot = _build_relative_strength_snapshot(raw_df, start_time, end_time)

    df = calculate_technical_indicators(df)

    clean_df = df.dropna(
        subset=[
            "ma20", "ma50", "rsi14", "macd", "macd_signal",
            "macd_hist", "bb_upper", "bb_lower", "atr14", "volume_ratio"
        ]
    ).copy()

    if clean_df.empty:
        logger.warning(f"Not enough data to calculate indicators | instrument={instrument}")
        return {
            "error": "Not enough data to calculate technical indicators"
        }

    last_row = clean_df.iloc[-1]

    chart_df = clean_df[["datetime", "close", "ma20", "ma50", "bb_upper", "bb_lower"]].copy()
    chart_data = {
        "dates": [str(x)[:10] for x in chart_df["datetime"].tolist()],
        "close": [_safe_round(x) for x in chart_df["close"].tolist()],
        "ma20": [_safe_round(x) for x in chart_df["ma20"].tolist()],
        "ma50": [_safe_round(x) for x in chart_df["ma50"].tolist()],
        "bb_upper": [_safe_round(x) for x in chart_df["bb_upper"].tolist()],
        "bb_lower": [_safe_round(x) for x in chart_df["bb_lower"].tolist()],
    }

    table_df = clean_df[
        [
            "datetime", "open", "high", "low", "close", "volume",
            "ma20", "ma50", "ema20", "ema50",
            "rsi14", "macd", "macd_signal", "macd_hist",
            "bb_upper", "bb_lower", "bb_width",
            "atr14", "volume_ratio",
            "stoch_k", "stoch_d",
            "plus_di14", "minus_di14", "adx14",
            "volatility20",
            "breakout_high_20", "breakout_low_20",
            "technical_score", "final_signal", "reasons"
        ]
    ].copy()

    try:
        news_result = fetch_ai_news(instrument, 8)
    except Exception as news_error:
        news_result = _fallback_news_payload(f"News unavailable: {news_error}")

    technical_score = int(last_row["technical_score"]) if not pd.isna(last_row["technical_score"]) else 0
    technical_signal = last_row["final_signal"]
    news_score = int(news_result.get("ai_news_score", news_result.get("news_score", 0)))
    combined_score = technical_score + news_score
    signal = _combined_signal(combined_score)

    ml_result = {}
    if predict_ml_latest is not None:
        try:
            ml_result = predict_ml_latest(
                instrument=instrument,
                start_date=start_time,
                end_date=end_time
            )
        except Exception as ml_error:
            ml_result = {"error": str(ml_error)}

    ml_score = _ml_score_from_result(ml_result)
    regime_result = _detect_market_regime(last_row)

    multi_timeframe = {
        "daily": _build_timeframe_snapshot(raw_df, "D", "DAILY"),
        "weekly": _build_timeframe_snapshot(raw_df, "W-FRI", "WEEKLY"),
        "monthly": _build_timeframe_snapshot(raw_df, "ME", "MONTHLY"),
    }

    mtf_result = _mtf_score_from_map(multi_timeframe)
    mtf_score = int(mtf_result.get("mtf_score", 0))
    mtf_alignment = mtf_result.get("mtf_alignment", "Daily=NEUTRAL | Weekly=NEUTRAL | Monthly=NEUTRAL")
    rs_score = int(rs_snapshot.get("rs_score", 0))

    enhanced_combined_score = combined_score + ml_score + mtf_score + rs_score
    enhanced_signal = _combined_signal(enhanced_combined_score)

    table_data = []
    last_date_str = str(last_row["datetime"])[:10]

    for _, row in table_df.iterrows():
        row_date_str = str(row["datetime"])[:10]
        row_signal = row["final_signal"]
        final_signal = enhanced_signal if row_date_str == last_date_str else row_signal
        trade_plan = _build_trade_plan(row, final_signal)

        table_data.append({
            "date": row_date_str,
            "open": _safe_round(row["open"]),
            "high": _safe_round(row["high"]),
            "low": _safe_round(row["low"]),
            "close": _safe_round(row["close"]),
            "volume": _safe_round(row["volume"], 2),
            "ma20": _safe_round(row["ma20"]),
            "ma50": _safe_round(row["ma50"]),
            "ema20": _safe_round(row["ema20"]),
            "ema50": _safe_round(row["ema50"]),
            "rsi14": _safe_round(row["rsi14"]),
            "macd": _safe_round(row["macd"]),
            "macd_signal": _safe_round(row["macd_signal"]),
            "macd_hist": _safe_round(row["macd_hist"]),
            "bb_upper": _safe_round(row["bb_upper"]),
            "bb_lower": _safe_round(row["bb_lower"]),
            "bb_width": _safe_round(row["bb_width"]),
            "atr14": _safe_round(row["atr14"]),
            "volume_ratio": _safe_round(row["volume_ratio"]),
            "stoch_k": _safe_round(row["stoch_k"]),
            "stoch_d": _safe_round(row["stoch_d"]),
            "plus_di14": _safe_round(row["plus_di14"]),
            "minus_di14": _safe_round(row["minus_di14"]),
            "adx14": _safe_round(row["adx14"]),
            "volatility20": _safe_round(row["volatility20"]),
            "breakout_high_20": _safe_round(row["breakout_high_20"]),
            "breakout_low_20": _safe_round(row["breakout_low_20"]),
            "support": trade_plan["support"],
            "resistance": trade_plan["resistance"],
            "atr_stop": trade_plan["atr_stop"],
            "atr_target": trade_plan["atr_target"],
            "risk_reward": trade_plan["risk_reward"],
            "technical_score": int(row["technical_score"]) if not pd.isna(row["technical_score"]) else None,
            "technical_signal": row_signal,
            "signal": final_signal,
            "reasons": row["reasons"],
        })

    trade_plan = _build_trade_plan(last_row, enhanced_signal)

    logger.info(
        f"run_analysis completed | instrument={instrument} | signal={signal} | "
        f"enhanced_signal={enhanced_signal} | regime={regime_result.get('market_regime')} | "
        f"trend_mode={regime_result.get('trend_mode')} | technical_score={technical_score} | "
        f"news_score={news_score} | ml_score={ml_score} | mtf_score={mtf_score} | rs_score={rs_score} | combined_score={combined_score} | "
        f"enhanced_combined_score={enhanced_combined_score} | close={_safe_round(last_row['close'])}"
    )

    return {
        "instrument": instrument,
        "close": _safe_round(last_row["close"]),
        "ma20": _safe_round(last_row["ma20"]),
        "ma50": _safe_round(last_row["ma50"]),
        "ema20": _safe_round(last_row["ema20"]),
        "ema50": _safe_round(last_row["ema50"]),
        "rsi14": _safe_round(last_row["rsi14"]),
        "macd": _safe_round(last_row["macd"]),
        "macd_signal": _safe_round(last_row["macd_signal"]),
        "macd_hist": _safe_round(last_row["macd_hist"]),
        "bb_upper": _safe_round(last_row["bb_upper"]),
        "bb_lower": _safe_round(last_row["bb_lower"]),
        "bb_width": _safe_round(last_row["bb_width"]),
        "atr14": _safe_round(last_row["atr14"]),
        "volume_ratio": _safe_round(last_row["volume_ratio"]),
        "stoch_k": _safe_round(last_row["stoch_k"]),
        "stoch_d": _safe_round(last_row["stoch_d"]),
        "plus_di14": _safe_round(last_row["plus_di14"]),
        "minus_di14": _safe_round(last_row["minus_di14"]),
        "adx14": _safe_round(last_row["adx14"]),
        "volatility20": _safe_round(last_row["volatility20"]),
        "high_52w": _safe_round(last_row["high_52w"]),
        "low_52w": _safe_round(last_row["low_52w"]),
        "dist_from_52w_high_pct": _safe_round(last_row["dist_from_52w_high_pct"]),
        "dist_from_52w_low_pct": _safe_round(last_row["dist_from_52w_low_pct"]),
        "gap_pct": _safe_round(last_row["gap_pct"]),
        "gap_signal": last_row.get("gap_signal"),
        "candle_signal": last_row.get("candle_signal"),
        "doji": bool(last_row.get("doji")) if pd.notna(last_row.get("doji")) else False,
        "hammer": bool(last_row.get("hammer")) if pd.notna(last_row.get("hammer")) else False,
        "shooting_star": bool(last_row.get("shooting_star")) if pd.notna(last_row.get("shooting_star")) else False,
        "bullish_engulfing": bool(last_row.get("bullish_engulfing")) if pd.notna(last_row.get("bullish_engulfing")) else False,
        "bearish_engulfing": bool(last_row.get("bearish_engulfing")) if pd.notna(last_row.get("bearish_engulfing")) else False,
        "squeeze_ready": bool(last_row.get("squeeze_ready")) if pd.notna(last_row.get("squeeze_ready")) else False,
        "trend_quality_score": int(last_row.get("trend_quality_score")) if pd.notna(last_row.get("trend_quality_score")) else 0,
        "support": trade_plan["support"],
        "resistance": trade_plan["resistance"],
        "atr_stop": trade_plan["atr_stop"],
        "atr_target": trade_plan["atr_target"],
        "risk_reward": trade_plan["risk_reward"],
        "technical_score": technical_score,
        "technical_signal": technical_signal,
        "news_score": news_result.get("news_score", 0),
        "news_sentiment": news_result.get("news_sentiment", "NEUTRAL"),
        "ai_enabled": news_result.get("ai_enabled", False),
        "ai_summary": news_result.get("ai_summary", ""),
        "ai_news_score": news_score,
        "ai_news_sentiment": news_result.get("ai_news_sentiment", news_result.get("news_sentiment", "NEUTRAL")),
        "ai_error": news_result.get("ai_error"),
        "combined_score": combined_score,
        "signal": signal,
        "ml_enabled": predict_ml_latest is not None,
        "ml_class": ml_result.get("ml_class"),
        "ml_signal": ml_result.get("ml_signal"),
        "ml_confidence": ml_result.get("ml_confidence"),
        "ml_prob_sell": ml_result.get("ml_prob_sell"),
        "ml_prob_hold": ml_result.get("ml_prob_hold"),
        "ml_prob_buy": ml_result.get("ml_prob_buy"),
        "ml_error": ml_result.get("error"),
        "ml_score": ml_score,
        "market_regime": regime_result.get("market_regime"),
        "trend_mode": regime_result.get("trend_mode"),
        "regime_score": regime_result.get("regime_score"),
        "multi_timeframe": multi_timeframe,
        "mtf_score": mtf_score,
        "mtf_alignment": mtf_alignment,
        "rs_benchmark": rs_snapshot.get("rs_benchmark"),
        "rs_spy_20": rs_snapshot.get("rs_spy_20"),
        "rs_spy_63": rs_snapshot.get("rs_spy_63"),
        "rs_state": rs_snapshot.get("rs_state"),
        "rs_score": rs_score,
        "enhanced_combined_score": enhanced_combined_score,
        "enhanced_signal": enhanced_signal,
        "reasons": last_row["reasons"],
        "articles_count": news_result.get("articles_count", 0),
        "positive_count": news_result.get("positive_count", 0),
        "negative_count": news_result.get("negative_count", 0),
        "neutral_count": news_result.get("neutral_count", 0),
        "news_items": news_result.get("news_items", []),
        "date": str(last_row["datetime"])[:10],
        "start_date": start_time,
        "end_date": end_time,
        "chart_data": chart_data,
        "table_data": table_data
    }


def run_analysis(instrument="AAPL", start_date="2024-01-01", end_date="2026-04-02"):
    return get_latest_signal(
        instrument=instrument,
        start_time=start_date,
        end_time=end_date
    )
