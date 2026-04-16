"""Strategy domain service facade.

Signals and ranking logic live here. The output of this layer should remain
deterministic and produce analysis results or trading intents, not broker
orders.
"""

from backend.app.services.cached_analysis import (
    get_base_analysis_result,
    get_base_analysis_results_batch,
    get_ranked_analysis_result,
)
from backend.app.services.job_workflows import run_ranking_scan_workflow, run_scan_workflow
from core.ranking_service import rank_analysis


def rank_single_analysis(instrument: str, start_date: str, end_date: str) -> dict:
    result = get_base_analysis_result(instrument, start_date, end_date)
    if "error" in result:
        return result
    return rank_analysis(result)


__all__ = [
    "get_base_analysis_result",
    "get_base_analysis_results_batch",
    "get_ranked_analysis_result",
    "rank_single_analysis",
    "run_ranking_scan_workflow",
    "run_scan_workflow",
]
