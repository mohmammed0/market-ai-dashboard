from __future__ import annotations

import numpy as np
import pandas as pd

from technical_engine import calculate_technical_indicators

from backend.app.services.market_data import _load_local_csv


FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "log_return_1d",
    "rolling_vol_5",
    "rolling_vol_20",
    "atr14",
    "atr_pct",
    "trend_gap_ma20",
    "trend_gap_ma50",
    "rsi14",
    "macd",
    "macd_signal",
    "macd_hist",
    "cci20",
    "mfi14",
    "roc10",
    "adx14",
    "plus_di14",
    "minus_di14",
    "stoch_k",
    "stoch_d",
    "williams_r14",
    "obv",
    "volume_ratio",
    "volume_pressure",
    "squeeze_flag",
    "trend_quality_score",
    "technical_score",
    "mtf_proxy",
    "gap_pct",
    "distance_52w_high_pct",
    "distance_52w_low_pct",
    "rolling_max_20_gap",
    "rolling_min_20_gap",
    "drawdown_20_pct",
    "benchmark_return_5d",
    "relative_strength_5d",
]


def _safe_col(df: pd.DataFrame, name: str, default=0.0):
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(default, index=df.index, dtype="float64")


def build_feature_frame(raw_df: pd.DataFrame, instrument="AAPL", benchmark_symbol="SPY"):
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    df = raw_df.copy()
    if "datetime" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "datetime"})
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    df["instrument"] = instrument
    df = calculate_technical_indicators(df)

    df["return_1d"] = df["close"].pct_change()
    df["return_5d"] = df["close"].pct_change(5)
    df["log_return_1d"] = np.log1p(df["return_1d"].fillna(0.0))
    df["rolling_vol_5"] = df["return_1d"].rolling(5).std()
    df["rolling_vol_20"] = df["return_1d"].rolling(20).std()
    df["atr_pct"] = _safe_col(df, "atr14") / df["close"].replace(0, np.nan)
    df["trend_gap_ma20"] = (df["close"] / _safe_col(df, "ma20").replace(0, np.nan)) - 1.0
    df["trend_gap_ma50"] = (df["close"] / _safe_col(df, "ma50").replace(0, np.nan)) - 1.0
    df["cci20"] = ((_safe_col(df, "close") - _safe_col(df, "ma20")) / (_safe_col(df, "atr14").replace(0, np.nan))) * 0.015
    df["mfi14"] = ((_safe_col(df, "high") + _safe_col(df, "low") + _safe_col(df, "close")) / 3.0 * _safe_col(df, "volume")).rolling(14).mean()
    df["roc10"] = df["close"].pct_change(10)
    high_roll = _safe_col(df, "high").rolling(14).max()
    low_roll = _safe_col(df, "low").rolling(14).min()
    df["williams_r14"] = ((high_roll - df["close"]) / (high_roll - low_roll).replace(0, np.nan)) * -100.0
    direction = np.sign(df["close"].diff().fillna(0.0))
    df["obv"] = (direction * _safe_col(df, "volume")).fillna(0.0).cumsum()
    df["volume_pressure"] = (_safe_col(df, "volume_ratio") - 1.0) * np.sign(df["return_1d"].fillna(0.0))
    df["squeeze_flag"] = (_safe_col(df, "bb_width") < _safe_col(df, "bb_width").rolling(20).median()).astype(float)
    df["mtf_proxy"] = np.sign(_safe_col(df, "ema20") - _safe_col(df, "ema50")) + np.sign(_safe_col(df, "ma20") - _safe_col(df, "ma50"))
    df["gap_pct"] = (_safe_col(df, "open") / _safe_col(df, "close").shift(1).replace(0, np.nan)) - 1.0
    df["distance_52w_high_pct"] = (df["close"] / df["close"].rolling(252, min_periods=20).max()) - 1.0
    df["distance_52w_low_pct"] = (df["close"] / df["close"].rolling(252, min_periods=20).min()) - 1.0
    df["rolling_max_20_gap"] = (df["close"] / df["close"].rolling(20, min_periods=5).max()) - 1.0
    df["rolling_min_20_gap"] = (df["close"] / df["close"].rolling(20, min_periods=5).min()) - 1.0
    df["drawdown_20_pct"] = (df["close"] / df["close"].rolling(20, min_periods=5).max()) - 1.0

    benchmark_df = _load_local_csv(benchmark_symbol)
    if not benchmark_df.empty:
        benchmark_df["datetime"] = pd.to_datetime(benchmark_df["datetime"], errors="coerce")
        benchmark_df = benchmark_df.dropna(subset=["datetime"]).sort_values("datetime")
        benchmark_df["benchmark_return_5d"] = benchmark_df["close"].pct_change(5)
        merged = df[["datetime"]].merge(benchmark_df[["datetime", "benchmark_return_5d"]], on="datetime", how="left")
        df["benchmark_return_5d"] = merged["benchmark_return_5d"].fillna(0.0)
    else:
        df["benchmark_return_5d"] = 0.0

    df["relative_strength_5d"] = df["return_5d"].fillna(0.0) - df["benchmark_return_5d"].fillna(0.0)

    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0

    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].ffill().fillna(0.0)
    return df


def create_target_labels(df: pd.DataFrame, horizon_days=5, buy_threshold=0.02, sell_threshold=-0.02):
    dataset = df.copy()
    dataset["future_close"] = dataset["close"].shift(-int(horizon_days))
    dataset["future_return"] = (dataset["future_close"] / dataset["close"]) - 1.0
    dataset["target_class"] = 0
    dataset.loc[dataset["future_return"] >= float(buy_threshold), "target_class"] = 1
    dataset.loc[dataset["future_return"] <= float(sell_threshold), "target_class"] = -1
    return dataset
