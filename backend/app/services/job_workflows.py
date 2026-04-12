from __future__ import annotations

from backend.app.application.execution.service import refresh_signals
from backend.app.schemas.automation import AutomationRunRequest, StrategyEvaluationRequest
from backend.app.schemas.execution import PaperSignalRefreshRequest
from backend.app.schemas.intelligence import BatchInferenceRequest
from backend.app.schemas.research import BacktestRequest, ScanRequest
from backend.app.services.automation_hub import run_automation_job
from backend.app.services.cached_analysis import get_base_analysis_results_batch
from backend.app.services.signal_runtime import build_smart_analysis
from backend.app.services.strategy_lab import run_strategy_evaluation
from core.backtest_service import backtest_symbol_enhanced, run_vectorbt_backtest
from core.ranking_service import rank_scan_results, summarize_long_short


def run_automation_workflow(payload: dict) -> dict:
    request = AutomationRunRequest(**payload)
    return run_automation_job(
        job_name=request.job_name,
        dry_run=request.dry_run,
        preset=request.preset,
    )


def run_scan_workflow(payload: dict) -> dict:
    request = ScanRequest(**payload)
    rows = get_base_analysis_results_batch(request.symbols, request.start_date, request.end_date)
    ranked_rows = rank_scan_results(rows)
    return {
        "items": ranked_rows,
        "summary": {
            **summarize_long_short(ranked_rows, limit=3),
            "total_symbols": len(request.symbols),
            "successful_results": len([row for row in ranked_rows if str(row.get("signal", "")).upper() != "ERROR"]),
            "top_pick": next(
                (row.get("instrument") for row in ranked_rows if str(row.get("signal", "")).upper() != "ERROR"),
                None,
            ),
        },
    }


def run_ranking_scan_workflow(payload: dict) -> dict:
    request = ScanRequest(**payload)
    rows = [
        row
        for row in get_base_analysis_results_batch(request.symbols, request.start_date, request.end_date)
        if "error" not in row
    ]
    ranked_rows = rank_scan_results(rows)
    return {
        "items": ranked_rows,
        "summary": {
            **summarize_long_short(ranked_rows, limit=3),
            "total_symbols": len(request.symbols),
            "successful_results": len([row for row in ranked_rows if str(row.get("signal", "")).upper() != "ERROR"]),
            "top_pick": next(
                (row.get("instrument") for row in ranked_rows if str(row.get("signal", "")).upper() != "ERROR"),
                None,
            ),
        },
    }


def run_backtest_workflow(payload: dict) -> dict:
    request = BacktestRequest(**payload)
    return backtest_symbol_enhanced(
        instrument=request.instrument,
        start_date=request.start_date,
        end_date=request.end_date,
        hold_days=request.hold_days,
        min_technical_score=request.min_technical_score,
        buy_score_threshold=request.buy_score_threshold,
        sell_score_threshold=request.sell_score_threshold,
    )


def run_vectorbt_backtest_workflow(payload: dict) -> dict:
    request = BacktestRequest(**payload)
    return run_vectorbt_backtest(
        instrument=request.instrument,
        start_date=request.start_date,
        end_date=request.end_date,
        hold_days=request.hold_days,
        min_technical_score=request.min_technical_score,
        buy_score_threshold=request.buy_score_threshold,
        sell_score_threshold=request.sell_score_threshold,
    )


def run_strategy_evaluation_workflow(payload: dict) -> dict:
    request = StrategyEvaluationRequest(**payload)
    return run_strategy_evaluation(
        instrument=request.instrument,
        start_date=request.start_date,
        end_date=request.end_date,
        hold_days=request.hold_days,
        include_modes=request.include_modes,
        windows=request.windows,
    )


def run_paper_signal_refresh_workflow(payload: dict) -> dict:
    request = PaperSignalRefreshRequest(**payload)
    return refresh_signals(
        symbols=request.symbols,
        mode=request.mode,
        start_date=request.start_date,
        end_date=request.end_date,
        auto_execute=request.auto_execute,
        quantity=request.quantity,
    )


def run_batch_inference_workflow(payload: dict) -> dict:
    request = BatchInferenceRequest(**payload)
    items = []
    for symbol in request.symbols:
        try:
            items.append(
                build_smart_analysis(
                    symbol,
                    request.start_date,
                    request.end_date,
                    include_dl=request.include_dl,
                    include_ensemble=request.include_ensemble,
                )
            )
        except Exception as exc:
            items.append({"instrument": symbol, "error": str(exc), "signal": "ERROR"})
    return {"items": rank_scan_results(items)}
