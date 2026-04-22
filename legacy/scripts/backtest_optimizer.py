
import pandas as pd
from itertools import product

from legacy.engines.backtest_engine import backtest_symbol_enhanced


def optimize_symbol(
    instrument="AAPL",
    start_date="2024-01-01",
    end_date="2026-04-02",
    hold_days_list=(5, 10, 15, 20),
    min_technical_scores=(2, 3),
    buy_score_thresholds=(3, 4, 5),
    sell_score_thresholds=(4, 5, 6),
):
    rows = []

    for hold_days, min_score, buy_th, sell_th in product(
        hold_days_list,
        min_technical_scores,
        buy_score_thresholds,
        sell_score_thresholds,
    ):
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
            continue

        trades = int(result.get("trades", 0) or 0)
        overall_win_rate = result.get("overall_win_rate_pct")
        avg_trade_return = result.get("avg_trade_return_pct")
        buy_win_rate = result.get("buy_win_rate_pct")
        sell_win_rate = result.get("sell_win_rate_pct")

        if trades <= 0:
            continue

        stability_score = 0.0
        if overall_win_rate is not None:
            stability_score += float(overall_win_rate)
        if avg_trade_return is not None:
            stability_score += float(avg_trade_return) * 10.0
        stability_score += min(trades, 200) * 0.03

        rows.append({
            "instrument": instrument,
            "hold_days": hold_days,
            "min_technical_score": min_score,
            "buy_score_threshold": buy_th,
            "sell_score_threshold": sell_th,
            "trades": trades,
            "overall_win_rate_pct": overall_win_rate,
            "buy_win_rate_pct": buy_win_rate,
            "sell_win_rate_pct": sell_win_rate,
            "avg_trade_return_pct": avg_trade_return,
            "median_trade_return_pct": result.get("median_trade_return_pct"),
            "best_trade_pct": result.get("best_trade_pct"),
            "worst_trade_pct": result.get("worst_trade_pct"),
            "avg_technical_score": result.get("avg_technical_score"),
            "avg_mtf_score": result.get("avg_mtf_score"),
            "avg_rs_score": result.get("avg_rs_score"),
            "avg_trend_quality_score": result.get("avg_trend_quality_score"),
            "stability_score": round(stability_score, 4),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["avg_trade_return_pct", "overall_win_rate_pct", "trades", "stability_score"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    return df


if __name__ == "__main__":
    df = optimize_symbol("AAPL", "2024-01-01", "2026-04-02")
    if df.empty:
        print("No optimization results")
    else:
        df.to_csv("optimizer_results_AAPL.csv", index=False, encoding="utf-8-sig")
        print(df.head(15).to_string(index=False))
        print("")
        print("Saved: optimizer_results_AAPL.csv")
