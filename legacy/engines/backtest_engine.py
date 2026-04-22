
import pandas as pd

from legacy.engines.technical_engine import calculate_technical_indicators
from legacy.engines.analysis_engine import (
    _build_timeframe_snapshot,
    _mtf_score_from_map,
    _build_relative_strength_snapshot,
    _combined_signal,
)
from core.source_data import load_symbol_source_data


def _safe_round(value, digits=4):
    if pd.isna(value):
        return None
    return round(float(value), digits)


def _load_source_data(instrument, start_date, end_date):
    instrument = str(instrument).upper().strip()
    result = load_symbol_source_data(instrument, start_date=start_date, end_date=end_date, persist_on_fetch=True)
    if result.error:
        return None, result.error
    if result.frame is None or result.frame.empty:
        return None, f"No data found for {instrument} from {start_date} to {end_date}"

    df = result.frame.rename(columns={"date": "datetime"}).copy()
    return df[["datetime", "instrument", "open", "high", "low", "close", "volume"]].copy(), None


def backtest_symbol(instrument="AAPL", start_date="2024-01-01", end_date="2026-04-02", hold_days=10, min_score=2):
    raw_df, error = _load_source_data(instrument, start_date, end_date)
    if error:
        return {"error": error}

    df = calculate_technical_indicators(raw_df)
    df = df.dropna(subset=["close", "technical_score", "final_signal"]).copy()

    if df.empty:
        return {"error": "No backtest-ready rows after indicators"}

    df["future_close"] = df["close"].shift(-hold_days)
    df["future_return_pct"] = ((df["future_close"] / df["close"]) - 1.0) * 100

    df["direction"] = 0
    df.loc[df["final_signal"] == "BUY", "direction"] = 1
    df.loc[df["final_signal"] == "SELL", "direction"] = -1

    df["qualified"] = (df["direction"] != 0) & (df["technical_score"].abs() >= int(min_score))
    trades = df[df["qualified"] & df["future_return_pct"].notna()].copy()

    if trades.empty:
        return {
            "instrument": instrument,
            "hold_days": int(hold_days),
            "min_score": int(min_score),
            "total_rows": int(len(df)),
            "trades": 0,
            "error": None,
            "message": "No qualified trades for current filters",
            "events": [],
        }

    trades["trade_return_pct"] = trades["direction"] * trades["future_return_pct"]
    trades["win"] = trades["trade_return_pct"] > 0

    buy_trades = trades[trades["final_signal"] == "BUY"].copy()
    sell_trades = trades[trades["final_signal"] == "SELL"].copy()

    def _mean_or_none(series):
        if series is None or len(series) == 0:
            return None
        return _safe_round(series.mean())

    def _rate_or_none(mask_series):
        if mask_series is None or len(mask_series) == 0:
            return None
        return _safe_round(mask_series.mean() * 100)

    summary = {
        "instrument": instrument,
        "start_date": start_date,
        "end_date": end_date,
        "hold_days": int(hold_days),
        "min_score": int(min_score),
        "total_rows": int(len(df)),
        "trades": int(len(trades)),
        "buy_trades": int(len(buy_trades)),
        "sell_trades": int(len(sell_trades)),
        "overall_win_rate_pct": _rate_or_none(trades["win"]),
        "buy_win_rate_pct": _rate_or_none(buy_trades["future_return_pct"] > 0),
        "sell_win_rate_pct": _rate_or_none(sell_trades["future_return_pct"] < 0),
        "avg_trade_return_pct": _mean_or_none(trades["trade_return_pct"]),
        "median_trade_return_pct": _safe_round(trades["trade_return_pct"].median()),
        "avg_buy_forward_return_pct": _mean_or_none(buy_trades["future_return_pct"]),
        "avg_sell_forward_return_pct": _mean_or_none(sell_trades["future_return_pct"]),
        "best_trade_pct": _safe_round(trades["trade_return_pct"].max()),
        "worst_trade_pct": _safe_round(trades["trade_return_pct"].min()),
        "avg_technical_score": _mean_or_none(trades["technical_score"]),
        "last_signal": str(df.iloc[-1]["final_signal"]),
        "last_score": int(df.iloc[-1]["technical_score"]) if pd.notna(df.iloc[-1]["technical_score"]) else None,
        "error": None,
    }

    events = trades[
        [
            "datetime", "instrument", "close", "technical_score", "final_signal",
            "future_close", "future_return_pct", "trade_return_pct", "win", "reasons"
        ]
    ].copy()

    events["datetime"] = events["datetime"].astype(str).str[:10]

    summary["events"] = events.to_dict(orient="records")
    return summary


def save_backtest_events_csv(result, file_path="backtest_events.csv"):
    events = result.get("events", [])
    if not events:
        return None
    df = pd.DataFrame(events)
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    return file_path



def backtest_symbol_enhanced(
    instrument="AAPL",
    start_date="2024-01-01",
    end_date="2026-04-02",
    hold_days=10,
    min_technical_score=2,
    buy_score_threshold=3,
    sell_score_threshold=4,
):
    raw_df, error = _load_source_data(instrument, start_date, end_date)
    if error:
        return {"error": error}

    raw_df = raw_df.sort_values("datetime").reset_index(drop=True)
    if raw_df.empty:
        return {"error": "No raw data for enhanced backtest"}

    benchmark_df, _ = _load_source_data("SPY", start_date, end_date)
    if benchmark_df is not None and not benchmark_df.empty:
        benchmark_df = benchmark_df.sort_values("datetime").reset_index(drop=True)

    events = []

    for idx in range(len(raw_df)):
        if idx + int(hold_days) >= len(raw_df):
            break

        hist_raw = raw_df.iloc[: idx + 1].copy()
        hist_df = calculate_technical_indicators(hist_raw)

        clean_hist = hist_df.dropna(subset=["close", "technical_score", "final_signal"]).copy()
        if clean_hist.empty:
            continue

        last_row = clean_hist.iloc[-1]

        try:
            technical_score = int(last_row["technical_score"]) if pd.notna(last_row["technical_score"]) else 0
        except Exception:
            technical_score = 0

        if abs(technical_score) < int(min_technical_score):
            continue

        last_date = pd.to_datetime(last_row["datetime"])
        last_date_str = str(last_date)[:10]

        multi_timeframe = {
            "daily": _build_timeframe_snapshot(hist_raw, "D", "DAILY"),
            "weekly": _build_timeframe_snapshot(hist_raw, "W-FRI", "WEEKLY"),
            "monthly": _build_timeframe_snapshot(hist_raw, "ME", "MONTHLY"),
        }

        mtf_result = _mtf_score_from_map(multi_timeframe)
        mtf_score = int(mtf_result.get("mtf_score", 0))
        mtf_alignment = mtf_result.get("mtf_alignment", "Daily=NEUTRAL | Weekly=NEUTRAL | Monthly=NEUTRAL")

        rs_snapshot = _build_relative_strength_snapshot(hist_raw, start_date, last_date_str, benchmark="SPY")
        rs_score = int(rs_snapshot.get("rs_score", 0))

        candle_signal = str(last_row.get("candle_signal", "NONE")).upper()
        trend_quality_score = int(last_row.get("trend_quality_score", 0)) if pd.notna(last_row.get("trend_quality_score")) else 0
        squeeze_ready = bool(last_row.get("squeeze_ready")) if pd.notna(last_row.get("squeeze_ready")) else False

        enhanced_combined_score = technical_score + mtf_score + rs_score
        enhanced_signal = _combined_signal(enhanced_combined_score)

        bullish_confirm = any([
            mtf_score > 0,
            rs_score > 0,
            trend_quality_score >= 1,
            candle_signal in ["HAMMER", "BULLISH_ENGULFING"],
            squeeze_ready and technical_score > 0,
        ])

        bearish_confirm = any([
            mtf_score < 0,
            rs_score < 0,
            trend_quality_score <= -1,
            candle_signal in ["SHOOTING_STAR", "BEARISH_ENGULFING"],
        ])

        if enhanced_signal == "BUY":
            if enhanced_combined_score < int(buy_score_threshold):
                continue
            if technical_score < int(min_technical_score):
                continue
            if not bullish_confirm:
                continue
        elif enhanced_signal == "SELL":
            if enhanced_combined_score > -int(sell_score_threshold):
                continue
            if technical_score > -int(min_technical_score):
                continue
            if not bearish_confirm:
                continue
        else:
            continue

        current_close = float(last_row["close"])
        future_close = float(raw_df.iloc[idx + int(hold_days)]["close"])
        future_return_pct = ((future_close / current_close) - 1.0) * 100.0

        direction = 1 if enhanced_signal == "BUY" else -1
        trade_return_pct = direction * future_return_pct
        win = trade_return_pct > 0

        events.append({
            "datetime": last_date_str,
            "instrument": instrument,
            "close": _safe_round(current_close),
            "technical_score": technical_score,
            "mtf_score": mtf_score,
            "rs_score": rs_score,
            "trend_quality_score": trend_quality_score,
            "candle_signal": candle_signal,
            "squeeze_ready": squeeze_ready,
            "enhanced_combined_score": int(enhanced_combined_score),
            "enhanced_signal": enhanced_signal,
            "mtf_alignment": mtf_alignment,
            "rs_state": rs_snapshot.get("rs_state"),
            "future_close": _safe_round(future_close),
            "future_return_pct": _safe_round(future_return_pct),
            "trade_return_pct": _safe_round(trade_return_pct),
            "win": bool(win),
            "reasons": str(last_row.get("reasons", "")),
        })

    if not events:
        return {
            "instrument": instrument,
            "start_date": start_date,
            "end_date": end_date,
            "hold_days": int(hold_days),
            "min_technical_score": int(min_technical_score),
            "buy_score_threshold": int(buy_score_threshold),
            "sell_score_threshold": int(sell_score_threshold),
            "trades": 0,
            "error": None,
            "message": "No qualified enhanced trades for current filters",
            "events": [],
        }

    trades = pd.DataFrame(events)
    buy_trades = trades[trades["enhanced_signal"] == "BUY"].copy()
    sell_trades = trades[trades["enhanced_signal"] == "SELL"].copy()

    def _mean_or_none(series):
        if series is None or len(series) == 0:
            return None
        return _safe_round(series.mean())

    def _rate_or_none(mask_series):
        if mask_series is None or len(mask_series) == 0:
            return None
        return _safe_round(mask_series.mean() * 100)

    summary = {
        "instrument": instrument,
        "start_date": start_date,
        "end_date": end_date,
        "hold_days": int(hold_days),
        "min_technical_score": int(min_technical_score),
        "buy_score_threshold": int(buy_score_threshold),
        "sell_score_threshold": int(sell_score_threshold),
        "trades": int(len(trades)),
        "buy_trades": int(len(buy_trades)),
        "sell_trades": int(len(sell_trades)),
        "overall_win_rate_pct": _rate_or_none(trades["win"]),
        "buy_win_rate_pct": _rate_or_none(buy_trades["future_return_pct"] > 0),
        "sell_win_rate_pct": _rate_or_none(sell_trades["future_return_pct"] < 0),
        "avg_trade_return_pct": _mean_or_none(trades["trade_return_pct"]),
        "median_trade_return_pct": _safe_round(trades["trade_return_pct"].median()),
        "avg_buy_forward_return_pct": _mean_or_none(buy_trades["future_return_pct"]),
        "avg_sell_forward_return_pct": _mean_or_none(sell_trades["future_return_pct"]),
        "best_trade_pct": _safe_round(trades["trade_return_pct"].max()),
        "worst_trade_pct": _safe_round(trades["trade_return_pct"].min()),
        "avg_technical_score": _mean_or_none(trades["technical_score"]),
        "avg_mtf_score": _mean_or_none(trades["mtf_score"]),
        "avg_rs_score": _mean_or_none(trades["rs_score"]),
        "avg_trend_quality_score": _mean_or_none(trades["trend_quality_score"]),
        "last_signal": str(trades.iloc[-1]["enhanced_signal"]),
        "last_score": int(trades.iloc[-1]["enhanced_combined_score"]),
        "error": None,
        "events": trades.to_dict(orient="records"),
    }

    return summary


def save_enhanced_backtest_events_csv(result, file_path="enhanced_backtest_events.csv"):
    events = result.get("events", [])
    if not events:
        return None
    df = pd.DataFrame(events)
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    return file_path


if __name__ == "__main__":
    from pprint import pprint
    result = backtest_symbol()
    preview = dict(result)
    preview.pop("events", None)
    pprint(preview)
