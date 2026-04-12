
import pandas as pd

from leaders_universe import LEADERS_SYMBOLS
from backtest_optimizer_light import optimize_symbol_light


def run_batch_optimizer():
    all_frames = []
    best_rows = []
    total = len(LEADERS_SYMBOLS)

    print(f"Starting leaders batch optimizer | symbols={total}", flush=True)

    for idx, symbol in enumerate(LEADERS_SYMBOLS, start=1):
        print(f"\n=== [{idx}/{total}] {symbol} ===", flush=True)

        try:
            df = optimize_symbol_light(
                instrument=symbol,
                start_date="2024-01-01",
                end_date="2026-04-02",
                hold_days_list=(5, 10),
                min_technical_scores=(2,),
                buy_score_thresholds=(3, 4),
                sell_score_thresholds=(4, 5),
            )

            if df is None or df.empty:
                print(f"{symbol}: no optimization results", flush=True)
                continue

            df = df.copy()
            df["rank_in_symbol"] = range(1, len(df) + 1)
            all_frames.append(df)

            best = df.iloc[0].to_dict()
            best_rows.append(best)

            print(
                f"{symbol}: best | hold={best.get('hold_days')} | "
                f"buy_th={best.get('buy_score_threshold')} | "
                f"sell_th={best.get('sell_score_threshold')} | "
                f"trades={best.get('trades')} | "
                f"win_rate={best.get('overall_win_rate_pct')} | "
                f"avg_trade_return={best.get('avg_trade_return_pct')}",
                flush=True
            )
        except Exception as e:
            print(f"{symbol}: error | {e}", flush=True)

    if not all_frames:
        print("\nNo batch optimization results")
        return

    all_df = pd.concat(all_frames, ignore_index=True)
    best_df = pd.DataFrame(best_rows)

    all_df = all_df.sort_values(
        by=["instrument", "avg_trade_return_pct", "overall_win_rate_pct", "trades"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)

    best_df = best_df.sort_values(
        by=["avg_trade_return_pct", "overall_win_rate_pct", "trades"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    all_file = "leaders_optimizer_all.csv"
    best_file = "leaders_optimizer_best.csv"

    all_df.to_csv(all_file, index=False, encoding="utf-8-sig")
    best_df.to_csv(best_file, index=False, encoding="utf-8-sig")

    print("\n===== BEST PER SYMBOL =====")
    print(best_df.to_string(index=False))
    print("")
    print(f"Saved: {all_file}")
    print(f"Saved: {best_file}")


if __name__ == "__main__":
    run_batch_optimizer()
