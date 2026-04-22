from legacy.engines.ranking_engine import (
    _confidence_score as _legacy_confidence_score,
    _load_best_setup_map,
    _safe_float,
    _safe_int,
    _signal_bias,
    build_ranked_scan_rows,
    invalidate_best_setup_cache,
    rank_analysis_result,
    summarize_top_candidates_by_signal,
)


def confidence_score(*args, **kwargs):
    return _legacy_confidence_score(*args, **kwargs)


def load_best_setup_map():
    return _load_best_setup_map()


def safe_float(value, default=0.0):
    return _safe_float(value, default)


def safe_int(value, default=0):
    return _safe_int(value, default)


def signal_bias(payload: dict) -> int:
    return _signal_bias(payload)


__all__ = [
    "build_ranked_scan_rows",
    "confidence_score",
    "invalidate_best_setup_cache",
    "load_best_setup_map",
    "rank_analysis_result",
    "safe_float",
    "safe_int",
    "signal_bias",
    "summarize_top_candidates_by_signal",
]
