
import pandas as pd
from pathlib import Path

try:
    import yfinance as yf
except Exception as e:
    raise SystemExit(f"yfinance not installed: {e}")

LEADERS = [
    "SPY",
    "QQQ",
    "NVDA",
    "AAPL",
    "MSFT",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
]

OUT_DIR = Path("us_watchlist_source")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _flatten_columns(df):
    flat_cols = []
    for col in df.columns:
        if isinstance(col, tuple):
            parts = [str(x) for x in col if x is not None and str(x).strip() and str(x) != "None"]
            flat_cols.append("_".join(parts))
        else:
            flat_cols.append(str(col))
    df.columns = flat_cols
    return df


def _pick_column(columns, candidates):
    lower_map = {str(c).lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def download_symbol(symbol, start="2020-01-01", end="2026-04-03"):
    df = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        interval="1d",
        threads=False,
        group_by="column",
    )

    if df is None or df.empty:
        print(f"{symbol}: no data")
        return False

    df = df.reset_index()
    df = _flatten_columns(df)

    date_col = _pick_column(df.columns, ["Date", "Datetime", "date", "datetime"])
    open_col = _pick_column(df.columns, ["Open", f"Open_{symbol}", "open", f"open_{symbol}"])
    high_col = _pick_column(df.columns, ["High", f"High_{symbol}", "high", f"high_{symbol}"])
    low_col = _pick_column(df.columns, ["Low", f"Low_{symbol}", "low", f"low_{symbol}"])
    close_col = _pick_column(df.columns, ["Close", f"Close_{symbol}", "close", f"close_{symbol}"])
    volume_col = _pick_column(df.columns, ["Volume", f"Volume_{symbol}", "volume", f"volume_{symbol}"])

    chosen = {
        "date": date_col,
        "open": open_col,
        "high": high_col,
        "low": low_col,
        "close": close_col,
        "volume": volume_col,
    }

    missing = [k for k, v in chosen.items() if v is None]
    if missing:
        print(f"{symbol}: missing columns {missing} | raw_cols={list(df.columns)}")
        return False

    out_df = df[[date_col, open_col, high_col, low_col, close_col, volume_col]].copy()
    out_df.columns = ["date", "open", "high", "low", "close", "volume"]

    out_df["date"] = pd.to_datetime(out_df["date"], errors="coerce")
    out_df = out_df.dropna(subset=["date", "open", "high", "low", "close"]).copy()
    out_df = out_df.sort_values("date").reset_index(drop=True)

    out_file = OUT_DIR / f"{symbol}.csv"
    out_df.to_csv(out_file, index=False, encoding="utf-8-sig")
    print(f"{symbol}: saved {len(out_df)} rows -> {out_file}")
    return True


def main():
    ok = 0
    fail = 0

    for symbol in LEADERS:
        try:
            success = download_symbol(symbol)
            if success:
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            print(f"{symbol}: error | {e}")

    print("")
    print(f"completed | success={ok} | failed={fail}")


if __name__ == "__main__":
    main()
