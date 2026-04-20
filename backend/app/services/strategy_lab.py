"""Strategy Lab service.

Runs strategy evaluations with walk-forward validation, overfitting
measurement, reproducibility metadata, and optional experiment tracking.

Additions in architecture-alignment batch
-----------------------------------------
- ``compute_overfitting_metrics()`` — measures OOS decay and win-rate stability
- ``config_hash`` stored per run for reproducibility comparison
- ``experiment_tracker.log_experiment_run()`` called on every evaluation
- Rigor metadata (overfitting, config_hash, experiment_tracked) included in
  the return dict and persisted to ``metrics_json``
- Existing walk-forward, leaderboard, and model_runs logic is unchanged
"""

from __future__ import annotations

import math
from datetime import datetime
from uuid import uuid4

import pandas as pd

from backend.app.models import StrategyEvaluationRun
from backend.app.services.ml_lab import list_model_runs
from backend.app.services.signal_runtime import build_smart_analysis
from backend.app.services.storage import dumps_json, loads_json, session_scope
from core.backtest_service import backtest_symbol_enhanced, run_vectorbt_backtest
from core.source_data import load_symbol_source_data


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _rank_score(total_return_pct=0.0, win_rate_pct=0.0, max_drawdown_pct=0.0, expectancy_pct=0.0):
    return round(
        (_safe_float(total_return_pct) * 0.35)
        + (_safe_float(win_rate_pct) * 0.25)
        + (_safe_float(expectancy_pct) * 12.0)
        - (_safe_float(max_drawdown_pct) * 0.25),
        3,
    )


def _classic_summary(result: dict) -> dict:
    return {
        "strategy": "classic",
        "trades": int(result.get("trades", 0) or 0),
        "win_rate_pct": _safe_float(result.get("overall_win_rate_pct")),
        "avg_trade_return_pct": _safe_float(result.get("avg_trade_return_pct")),
        "total_return_pct": _safe_float(result.get("total_return_pct")),
        "max_drawdown_pct": _safe_float(result.get("max_drawdown_pct")),
    }


def _vectorbt_summary(result: dict) -> dict:
    returns_stats = result.get("returns_stats") or {}
    drawdown_stats = result.get("drawdown_stats") or {}
    return {
        "strategy": "vectorbt",
        "trades": int(result.get("trades", 0) or 0),
        "win_rate_pct": _safe_float(returns_stats.get("win_rate_pct")),
        "avg_trade_return_pct": _safe_float(returns_stats.get("avg_trade_return_pct")),
        "total_return_pct": _safe_float(returns_stats.get("total_return_pct")),
        "max_drawdown_pct": _safe_float(drawdown_stats.get("max_drawdown_pct")),
    }


def _smart_summary(result: dict, mode: str) -> dict:
    output = (
        result.get("ml_output") if mode == "ml"
        else result.get("dl_output") if mode == "dl"
        else result.get("ensemble_output")
    ) or {}
    return {
        "strategy": mode,
        "signal": output.get("signal"),
        "confidence": _safe_float(output.get("confidence")),
        "ensemble_score": _safe_float(output.get("ensemble_score")),
        "model_run_id": output.get("run_id"),
    }


def _walk_forward_windows(start_date: str, end_date: str, windows: int = 3):
    dates = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), periods=windows + 1)
    result = []
    for index in range(len(dates) - 1):
        result.append({
            "window": index + 1,
            "start_date": dates[index].date().isoformat(),
            "end_date": dates[index + 1].date().isoformat(),
        })
    return result


# ---------------------------------------------------------------------------
# Overfitting measurement (NEW)
# ---------------------------------------------------------------------------

def compute_overfitting_metrics(
    walk_forward: list[dict],
    full_period_return_pct: float,
) -> dict:
    """Measure out-of-sample decay and win-rate stability across windows.

    Returns a dict compatible with ``OverfittingMetrics`` contract.

    Fields
    ------
    train_return_pct     Full-period (in-sample) classic return.
    oos_avg_return_pct   Mean classic return across walk-forward windows.
    oos_decay_pct        Relative decay: (train - oos) / max(|train|, 1) * 100.
                         Positive means performance degraded OOS (expected).
                         > 40 triggers the overfit_flag.
    win_rate_stability   Stddev of classic_win_rate_pct across windows.
                         > 20 triggers the overfit_flag.
    overfit_flag         True if decay > 40 OR stability > 20 stddev.
    overfit_score        0–100: 100 = perfect, 0 = completely overfit.
    """
    if not walk_forward:
        return {
            "train_return_pct": round(full_period_return_pct, 3),
            "oos_avg_return_pct": 0.0,
            "oos_decay_pct": 0.0,
            "win_rate_stability": 0.0,
            "overfit_flag": False,
            "overfit_score": 100.0,
            "note": "No walk-forward windows available.",
        }

    window_returns = [_safe_float(w.get("classic_total_return_pct", 0)) for w in walk_forward]
    window_win_rates = [_safe_float(w.get("classic_win_rate_pct", 0)) for w in walk_forward]

    oos_avg = sum(window_returns) / len(window_returns)
    train = _safe_float(full_period_return_pct)
    denominator = max(abs(train), 1.0)
    oos_decay_pct = ((train - oos_avg) / denominator) * 100.0

    # Win-rate stability: population stddev across windows
    if len(window_win_rates) > 1:
        mean_wr = sum(window_win_rates) / len(window_win_rates)
        variance = sum((w - mean_wr) ** 2 for w in window_win_rates) / len(window_win_rates)
        stability_stddev = math.sqrt(variance)
    else:
        stability_stddev = 0.0

    overfit_flag = oos_decay_pct > 40.0 or stability_stddev > 20.0
    overfit_score = max(0.0, min(100.0, 100.0 - abs(oos_decay_pct) * 0.5 - stability_stddev * 0.5))

    if overfit_flag:
        note = (
            "High OOS decay or win-rate instability detected. "
            "The strategy may be overfit to the training period."
        )
    else:
        note = "OOS stability looks reasonable. Walk-forward performance held up."

    return {
        "train_return_pct": round(train, 3),
        "oos_avg_return_pct": round(oos_avg, 3),
        "oos_decay_pct": round(oos_decay_pct, 2),
        "win_rate_stability": round(stability_stddev, 2),
        "overfit_flag": overfit_flag,
        "overfit_score": round(overfit_score, 1),
        "note": note,
    }


def compute_lookahead_audit_metrics(
    *,
    instrument: str,
    start_date: str,
    end_date: str,
    hold_days: int,
    events: list[dict] | None,
) -> dict:
    """Stress test timing sensitivity by delaying entry to the next bar open.

    This is not a formal proof of lookahead bias. It is a practical audit that
    flags strategy outputs whose edge collapses when the entry is delayed by one
    bar, which is often a symptom of fragile timing or subtle leakage.
    """
    trade_events = list(events or [])
    if not trade_events:
        return {
            "mode": "next_bar_open_delay",
            "audited_trades": 0,
            "possible_leakage_flag": False,
            "note": "No enhanced trade events were available for a lookahead audit.",
        }

    source = load_symbol_source_data(
        instrument,
        start_date=start_date,
        end_date=end_date,
        persist_on_fetch=True,
    )
    if source.error or source.frame is None or source.frame.empty:
        return {
            "mode": "next_bar_open_delay",
            "audited_trades": 0,
            "possible_leakage_flag": False,
            "note": f"Could not load source data for audit: {source.error or 'empty frame'}",
        }

    raw_df = source.frame.rename(columns={"date": "datetime"}).copy()
    raw_df["datetime"] = pd.to_datetime(raw_df["datetime"], errors="coerce")
    raw_df = raw_df.dropna(subset=["datetime", "open", "close"]).sort_values("datetime").reset_index(drop=True)
    if raw_df.empty:
        return {
            "mode": "next_bar_open_delay",
            "audited_trades": 0,
            "possible_leakage_flag": False,
            "note": "Audit source frame is empty after normalization.",
        }

    index_by_day = {row["datetime"].date().isoformat(): idx for idx, row in raw_df.iterrows()}
    delayed_returns: list[float] = []
    current_returns: list[float] = []
    skipped = 0

    for event in trade_events:
        day_key = str(event.get("datetime") or "")[:10]
        idx = index_by_day.get(day_key)
        direction = 1 if str(event.get("enhanced_signal") or "").upper() == "BUY" else -1
        if idx is None or direction == 0:
            skipped += 1
            continue
        entry_idx = idx + 1
        exit_idx = entry_idx + max(int(hold_days), 1)
        if entry_idx >= len(raw_df) or exit_idx >= len(raw_df):
            skipped += 1
            continue
        entry_open = _safe_float(raw_df.iloc[entry_idx]["open"])
        exit_close = _safe_float(raw_df.iloc[exit_idx]["close"])
        if entry_open <= 0 or exit_close <= 0:
            skipped += 1
            continue
        delayed_return = direction * (((exit_close / entry_open) - 1.0) * 100.0)
        delayed_returns.append(delayed_return)
        current_returns.append(_safe_float(event.get("trade_return_pct")))

    if not delayed_returns:
        return {
            "mode": "next_bar_open_delay",
            "audited_trades": 0,
            "skipped_trades": skipped,
            "possible_leakage_flag": False,
            "note": "Audit could not compute delayed-entry trades from available data.",
        }

    current_avg = sum(current_returns) / len(current_returns)
    delayed_avg = sum(delayed_returns) / len(delayed_returns)
    current_win_rate = (sum(1 for value in current_returns if value > 0) / len(current_returns)) * 100.0
    delayed_win_rate = (sum(1 for value in delayed_returns if value > 0) / len(delayed_returns)) * 100.0
    denominator = max(abs(current_avg), 1.0)
    decay_pct = ((current_avg - delayed_avg) / denominator) * 100.0
    win_rate_drop_pct = current_win_rate - delayed_win_rate
    leakage_flag = decay_pct > 35.0 or win_rate_drop_pct > 20.0

    note = (
        "Delayed-entry performance degraded sharply; review signal timing for leakage or unrealistic same-bar fills."
        if leakage_flag
        else "Delayed-entry audit is within a reasonable range."
    )
    return {
        "mode": "next_bar_open_delay",
        "audited_trades": len(delayed_returns),
        "skipped_trades": skipped,
        "current_avg_trade_return_pct": round(current_avg, 4),
        "delayed_avg_trade_return_pct": round(delayed_avg, 4),
        "performance_decay_pct": round(decay_pct, 2),
        "current_win_rate_pct": round(current_win_rate, 2),
        "delayed_win_rate_pct": round(delayed_win_rate, 2),
        "win_rate_drop_pct": round(win_rate_drop_pct, 2),
        "possible_leakage_flag": leakage_flag,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def run_strategy_evaluation(
    instrument: str,
    start_date: str,
    end_date: str,
    hold_days: int = 10,
    include_modes: list[str] | None = None,
    windows: int = 3,
) -> dict:
    """Run a full strategy evaluation with walk-forward validation and rigor metrics.

    Returns the evaluation results dict including:
    - ``leaderboard``     — ranked strategy summaries
    - ``walk_forward``    — per-window walk-forward results
    - ``overfitting``     — OOS decay / overfit measurement
    - ``config_hash``     — stable hash of run parameters for reproducibility
    - ``experiment_tracked`` / ``experiment_backend`` — tracking status
    """
    include_modes = include_modes or ["classic", "vectorbt", "ml", "dl", "ensemble"]
    run_id = f"strategy-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"

    # ------------------------------------------------------------------
    # Reproducibility: stable config hash
    # ------------------------------------------------------------------
    run_params = {
        "instrument": instrument,
        "start_date": start_date,
        "end_date": end_date,
        "hold_days": hold_days,
        "include_modes": sorted(include_modes),
        "windows": windows,
    }
    from backend.app.services.experiment_tracker import config_hash as _config_hash  # noqa: PLC0415
    cfg_hash = _config_hash(run_params)

    # ------------------------------------------------------------------
    # Full-period backtests
    # ------------------------------------------------------------------
    classic = backtest_symbol_enhanced(
        instrument=instrument, start_date=start_date, end_date=end_date, hold_days=hold_days,
    )
    vectorbt = run_vectorbt_backtest(
        instrument=instrument, start_date=start_date, end_date=end_date, hold_days=hold_days,
    )
    smart = build_smart_analysis(instrument, start_date, end_date, include_dl=False, include_ensemble=True)

    summaries = []
    if "classic" in include_modes:
        row = _classic_summary(classic)
        row["robust_score"] = _rank_score(
            row["total_return_pct"], row["win_rate_pct"],
            row["max_drawdown_pct"], row["avg_trade_return_pct"],
        )
        summaries.append(row)
    if "vectorbt" in include_modes:
        row = _vectorbt_summary(vectorbt)
        row["robust_score"] = _rank_score(
            row["total_return_pct"], row["win_rate_pct"],
            row["max_drawdown_pct"], row["avg_trade_return_pct"],
        )
        summaries.append(row)
    for mode in ("ml", "dl", "ensemble"):
        if mode in include_modes:
            row = _smart_summary(smart, mode)
            row["robust_score"] = round(row.get("confidence", 0.0) * 0.6, 3)
            summaries.append(row)

    summaries.sort(key=lambda item: _safe_float(item.get("robust_score")), reverse=True)

    # ------------------------------------------------------------------
    # Walk-forward validation
    # ------------------------------------------------------------------
    walk_forward = []
    for window in _walk_forward_windows(start_date, end_date, windows=windows):
        classic_w = backtest_symbol_enhanced(
            instrument=instrument,
            start_date=window["start_date"],
            end_date=window["end_date"],
            hold_days=hold_days,
        )
        vectorbt_w = run_vectorbt_backtest(
            instrument=instrument,
            start_date=window["start_date"],
            end_date=window["end_date"],
            hold_days=hold_days,
        )
        walk_forward.append({
            **window,
            "classic_total_return_pct": _safe_float(classic_w.get("total_return_pct")),
            "classic_win_rate_pct": _safe_float(classic_w.get("overall_win_rate_pct")),
            "vectorbt_total_return_pct": _safe_float(
                (vectorbt_w.get("returns_stats") or {}).get("total_return_pct")
            ),
            "vectorbt_max_drawdown_pct": _safe_float(
                (vectorbt_w.get("drawdown_stats") or {}).get("max_drawdown_pct")
            ),
        })

    # ------------------------------------------------------------------
    # Overfitting measurement (NEW)
    # ------------------------------------------------------------------
    full_return_pct = _safe_float(classic.get("total_return_pct"))
    overfitting = compute_overfitting_metrics(walk_forward, full_return_pct)
    lookahead_audit = compute_lookahead_audit_metrics(
        instrument=instrument,
        start_date=start_date,
        end_date=end_date,
        hold_days=hold_days,
        events=classic.get("events") or [],
    )

    # ------------------------------------------------------------------
    # Experiment tracking (NEW)
    # ------------------------------------------------------------------
    experiment_result: dict = {}
    try:
        from backend.app.services.experiment_tracker import log_experiment_run  # noqa: PLC0415
        best_row = summaries[0] if summaries else {}
        experiment_result = log_experiment_run(
            experiment_name="strategy_lab",
            run_id=run_id,
            params=run_params,
            metrics={
                "best_robust_score": _safe_float(best_row.get("robust_score")),
                "classic_total_return_pct": full_return_pct,
                "oos_decay_pct": overfitting["oos_decay_pct"],
                "overfit_score": overfitting["overfit_score"],
            },
            tags={
                "instrument": instrument,
                "best_strategy": best_row.get("strategy", ""),
                "config_hash": cfg_hash,
            },
        )
    except Exception:
        experiment_result = {"backend": "failed"}

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------
    try:
        from backend.app.services.observability import record_strategy_evaluation  # noqa: PLC0415
        record_strategy_evaluation(instrument=instrument, status="completed")
    except Exception:
        pass

    metrics = {
        "best_strategy": summaries[0]["strategy"] if summaries else None,
        "strategies": summaries,
        "walk_forward": walk_forward,
        "overfitting": overfitting,
        "lookahead_audit": lookahead_audit,
        "config_hash": cfg_hash,
        "model_runs": {
            "ml": list_model_runs("ml")[:3],
            "dl": list_model_runs("dl")[:3],
        },
    }

    with session_scope() as session:
        session.add(StrategyEvaluationRun(
            run_id=run_id,
            instrument=instrument,
            status="completed",
            completed_at=datetime.utcnow(),
            config_json=dumps_json({
                **run_params,
                "config_hash": cfg_hash,
            }),
            metrics_json=dumps_json(metrics),
            leaderboard_json=dumps_json(summaries),
            notes="Additive strategy-lab comparison run with overfitting metrics.",
        ))

    return {
        "run_id": run_id,
        "instrument": instrument,
        "status": "completed",
        "leaderboard": summaries,
        "walk_forward": walk_forward,
        "best_strategy": metrics["best_strategy"],
        "model_runs": metrics["model_runs"],
        # Rigor additions
        "overfitting": overfitting,
        "lookahead_audit": lookahead_audit,
        "config_hash": cfg_hash,
        "experiment_tracked": experiment_result.get("backend") not in {None, "failed"},
        "experiment_backend": experiment_result.get("backend"),
    }


def list_strategy_evaluations(limit: int = 20) -> dict:
    limit = max(1, min(int(limit or 20), 100))
    with session_scope() as session:
        rows = (
            session.query(StrategyEvaluationRun)
            .order_by(StrategyEvaluationRun.started_at.desc())
            .limit(limit)
            .all()
        )
        items = [
            {
                "run_id": row.run_id,
                "instrument": row.instrument,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "leaderboard": loads_json(row.leaderboard_json),
                "metrics": loads_json(row.metrics_json),
            }
            for row in rows
        ]
    return {"items": items, "count": len(items)}
