from legacy.engines.ranking_engine import (
    _confidence_score as _legacy_confidence_score,
    build_ranked_scan_rows,
    rank_analysis_result,
    summarize_top_candidates_by_signal,
)


def confidence_score(*args, **kwargs):
    return _legacy_confidence_score(*args, **kwargs)


__all__ = [
    "build_ranked_scan_rows",
    "confidence_score",
    "rank_analysis_result",
    "summarize_top_candidates_by_signal",
]
