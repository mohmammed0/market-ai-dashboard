from core.legacy_adapters.ranking import (
    rank_analysis_result,
    build_ranked_scan_rows,
    summarize_top_candidates_by_signal,
)


def rank_analysis(result):
    return rank_analysis_result(result)


def rank_scan_results(results):
    return build_ranked_scan_rows(results)


def summarize_long_short(rows, limit=3):
    return {
        "top_longs": summarize_top_candidates_by_signal(rows, "BUY", limit=limit),
        "top_shorts": summarize_top_candidates_by_signal(rows, "SELL", limit=limit),
    }
