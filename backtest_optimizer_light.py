
import pandas as pd
from itertools import product

from backtest_engine import backtest_symbol_enhanced


def optimize_symbol_light(
    instrument="AAPL",
    start_date="2024-01-01",
    end_date="2026-04-02",
    hold_days_list=(5, 10),
    min_technical_scores=(2,),
    buy_score_thresholds=(3, 4),
    sell_score_thresholds=(4, 5),
):
    combos = list(product(
        hold_days_list,
        min_technical_scores,
        buy_score_thresholds,
        sell_score_thresholds,
    ))

    rows = []
    total = len(combos)

    print(f"Starting light optimizer | total_combos={total}")

    for idx, (hold_days, min_score, buy_th, sell_th) in enumerate(combos, start=1):
        print(
            f"[{idx}/{total}] hold={hold_days} | min_score={min_score} | "
            f"buy_th={buy_th} | sell_th={sell_th}",
            flush=True
        )

        result = backtest_symbol_enhanced(
            instrument=instrument,
            start_date=start_date,
            end_date=end_date,
            hold_days=hold_days,
            min_technical_score=min_score,
            buy_score_threshold=buy_th,
            sell_score_threshold=sell_th,
        )

        if result.get("error"):
            print(f"  skipped | error={result.get('error')}", flush=True)
            continue

        trades = int(result.get("trades", 0) or 0)
        if trades <= 0:
            print("  skipped | no trades", flush=True)
            continue

        overall_win_rate = result.get("overall_win_rate_pct")
        avg_trade_return = result.get("avg_trade_return_pct")

        stability_score = 0.0
        if overall_win_rate is not None:
            stability_score += float(overall_win_rate)
        if avg_trade_return is not None:
            stability_score += float(avg_trade_return) * 10.0
        stability_score += min(trades, 200) * 0.03

        row = {
            "instrument": instrument,
            "hold_days": hold_days,
            "min_technical_score": min_score,
            "buy_score_threshold": buy_th,
            "sell_score_threshold": sell_th,
            "trades": trades,
            "overall_win_rate_pct": overall_win_rate,
            "buy_win_rate_pct": result.get("buy_win_rate_pct"),
            "sell_win_rate_pct": result.get("sell_win_rate_pct"),
            "avg_trade_return_pct": avg_trade_return,
            "median_trade_return_pct": result.get("median_trade_return_pct"),
            "best_trade_pct": result.get("best_trade_pct"),
            "worst_trade_pct": result.get("worst_trade_pct"),
            "avg_technical_score": result.get("avg_technical_score"),
            "avg_mtf_score": result.get("avg_mtf_score"),
            "avg_rs_score": result.get("avg_rs_score"),
            "avg_trend_quality_score": result.get("avg_trend_quality_score"),
            "stability_score": round(stability_score, 4),
        }
        rows.append(row)

        print(
            f"  done | trades={trades} | win_rate={overall_win_rate} | "
            f"avg_trade_return={avg_trade_return}",
            flush=True
        )

    if not rows:
        print("No optimization results")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["avg_trade_return_pct", "overall_win_rate_pct", "trades", "stability_score"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    return df


if __name__ == "__main__":
    df = optimize_symbol_light("AAPL", "2024-01-01", "2026-04-02")
    if df.empty:
        print("No optimization results")
    else:
        out_file = "optimizer_results_AAPL_light.csv"
        df.to_csv(out_file, index=False, encoding="utf-8-sig")
        print("")
        print(df.to_string(index=False))
        print("")
        print(f"Saved: {out_file}")
