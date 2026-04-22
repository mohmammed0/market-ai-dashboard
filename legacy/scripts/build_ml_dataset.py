from pathlib import Path
import pandas as pd

from legacy.engines.technical_engine import calculate_technical_indicators

SOURCE_DIR = Path("us_watchlist_source")
OUTPUT_FILE = Path("ml_training_data.csv")


def build_symbol_dataset(csv_path: Path):
    instrument = csv_path.stem.upper()
    df = pd.read_csv(csv_path)

    if df.empty or "date" not in df.columns:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()

    needed = ["open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in df.columns:
            return pd.DataFrame()

    df = df.rename(columns={"date": "datetime"})
    df["instrument"] = instrument

    df = df[["datetime", "instrument", "open", "high", "low", "close", "volume"]].copy()
    df = calculate_technical_indicators(df)

    df["future_close_3d"] = df["close"].shift(-3)
    df["future_return_3d"] = (df["future_close_3d"] / df["close"]) - 1

    df["target_class"] = 0
    df.loc[df["future_return_3d"] > 0.02, "target_class"] = 1
    df.loc[df["future_return_3d"] < -0.02, "target_class"] = -1

    keep_cols = [
        "datetime", "instrument", "open", "high", "low", "close", "volume",
        "ma20", "ma50", "ema20", "ema50",
        "rsi14", "macd", "macd_signal", "macd_hist",
        "bb_upper", "bb_lower", "bb_width",
        "atr14", "volume_ratio",
        "stoch_k", "stoch_d",
        "plus_di14", "minus_di14", "adx14",
        "volatility20", "breakout_high_20", "breakout_low_20",
        "technical_score",
        "future_close_3d", "future_return_3d", "target_class"
    ]

    df = df[keep_cols].copy()
    df = df.dropna().reset_index(drop=True)
    return df


all_parts = []
for csv_path in sorted(SOURCE_DIR.glob("*.csv")):
    part = build_symbol_dataset(csv_path)
    if not part.empty:
        all_parts.append(part)

if not all_parts:
    raise SystemExit("No training rows built")

final_df = pd.concat(all_parts, ignore_index=True)
final_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

print("DATASET_READY")
print("rows=", len(final_df))
print("symbols=", final_df["instrument"].nunique())
print("class_counts=")
print(final_df["target_class"].value_counts().sort_index())
print("saved_to=", OUTPUT_FILE)
