from __future__ import annotations

from datetime import datetime, timedelta
import logging
from time import perf_counter
from uuid import uuid4

from backend.app.application.alerts.service import list_alert_history
from backend.app.application.broker.service import get_broker_summary
from backend.app.application.model_lifecycle.service import (
    promote_model_run,
    review_model_promotion,
    train_dl_models,
    train_ml_models,
)
from backend.app.application.portfolio.service import get_portfolio_exposure
from backend.app.config import (
    AUTOMATION_ALERT_SYMBOL_LIMIT,
    AUTOMATION_DEFAULT_PRESET,
    AUTOMATION_SYMBOL_LIMIT,
    AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT,
    AUTONOMOUS_HISTORY_LOOKBACK_DAYS,
    AUTONOMOUS_INCLUDE_DL,
    AUTONOMOUS_REFRESH_UNIVERSE,
    AUTONOMOUS_TRAIN_SYMBOL_LIMIT,
    DEFAULT_SAMPLE_SYMBOLS,
    ENABLE_AUTO_RETRAIN,
    ENABLE_AUTONOMOUS_CYCLE,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models import AutomationArtifact, AutomationRun, MarketUniverseSymbol
from backend.app.services.advanced_alerts import generate_advanced_alerts
from backend.app.services.breadth_engine import compute_market_breadth, compute_sector_rotation
from backend.app.services.continuous_learning import get_continuous_learning_runtime_snapshot
from backend.app.services.market_data import SOURCE_DIR, fetch_quote_snapshots, load_history
from backend.app.services.market_universe import refresh_market_universe, resolve_universe_preset
from backend.app.services.smart_watchlists import build_dynamic_watchlists
from backend.app.services.signal_runtime import build_smart_analysis
from backend.app.services.storage import dumps_json, loads_json, session_scope
from backend.app.services.trade_journal import list_trade_journal_entries

logger = get_logger(__name__)

JOB_NAMES = {
    "market_cycle": "Market Cycle",
    "alert_cycle": "Alert Cycle",
    "breadth_cycle": "Breadth Cycle",
    "retrain_cycle": "Retrain Cycle",
    "autonomous_cycle": "Autonomous Cycle",
    "daily_summary": "Daily Summary",
}


def _training_overlap_guard() -> dict | None:
    snapshot = get_continuous_learning_runtime_snapshot()
    owner = snapshot.get("owner") or {}
    if snapshot.get("runtime_state") not in {"starting", "running"}:
        return None
    if not owner.get("ownership_active"):
        return None
    return {
        "status": "guarded",
        "reason": "Skipped model training because the continuous learning worker is currently active.",
        "continuous_learning": {
            "runtime_state": snapshot.get("runtime_state"),
            "worker_id": owner.get("worker_id"),
            "pid": owner.get("pid"),
        },
    }


def _utc_today_iso() -> str:
    return datetime.utcnow().date().isoformat()


def _analysis_window() -> tuple[str, str]:
    return "2024-01-01", _utc_today_iso()


def _training_window() -> tuple[str, str]:
    return "2020-01-01", _utc_today_iso()


def _available_local_symbols() -> set[str]:
    if not SOURCE_DIR.exists():
        return set()
    return {
        path.stem.upper()
        for path in SOURCE_DIR.glob("*.csv")
        if path.is_file()
    }


def _preferred_local_symbols(preset: str) -> list[str]:
    local_symbols = sorted(_available_local_symbols())
    if not local_symbols:
        return []

    normalized_preset = str(preset or AUTOMATION_DEFAULT_PRESET).strip().upper()
    with session_scope() as session:
        query = session.query(MarketUniverseSymbol.symbol).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.is_test_issue.is_(False),
            MarketUniverseSymbol.symbol.in_(local_symbols),
        )
        if normalized_preset == "NASDAQ":
            query = query.filter(MarketUniverseSymbol.exchange == "NASDAQ")
        elif normalized_preset == "NYSE":
            query = query.filter(MarketUniverseSymbol.exchange.in_(["NYSE", "NYSE American", "NYSE Arca"]))
        elif normalized_preset == "ETF_ONLY":
            query = query.filter(MarketUniverseSymbol.is_etf.is_(True))
        rows = query.order_by(MarketUniverseSymbol.symbol.asc()).all()
    return [row[0] for row in rows]


def _select_symbols_for_cycle(preset: str, universe_symbols: list[str], desired_count: int) -> list[str]:
    desired_count = max(int(desired_count or 0), 1)
    preferred = _preferred_local_symbols(preset)
    if preferred:
        return preferred[:desired_count]
    fallback = [symbol for symbol in universe_symbols if symbol not in preferred]
    return fallback[:desired_count]


def _record_run(job_name: str, status: str, started_at: datetime, dry_run: bool, detail: str, artifacts: list[dict]) -> dict:
    run_id = f"automation-{job_name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    completed_at = datetime.utcnow()
    duration = round((completed_at - started_at).total_seconds(), 4) if isinstance(started_at, datetime) else None
    with session_scope() as session:
        session.add(AutomationRun(
            run_id=run_id,
            job_name=job_name,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            dry_run=dry_run,
            detail=detail,
            artifacts_count=len(artifacts),
        ))
        for artifact in artifacts:
            session.add(AutomationArtifact(
                run_id=run_id,
                job_name=job_name,
                artifact_type=artifact.get("artifact_type", "payload"),
                artifact_key=artifact.get("artifact_key"),
                payload_json=dumps_json(artifact.get("payload")),
            ))
    return {
        "run_id": run_id,
        "job_name": job_name,
        "status": status,
        "detail": detail,
        "artifacts": artifacts,
        "completed_at": completed_at.isoformat(),
        "dry_run": dry_run,
    }


def _build_ranked_candidates(symbols: list[str], start_date: str, end_date: str, include_dl: bool = True, include_ensemble: bool = True) -> list[dict]:
    ranked = []
    for symbol in symbols:
        try:
            ranked.append(
                build_smart_analysis(
                    symbol,
                    start_date,
                    end_date,
                    include_dl=include_dl,
                    include_ensemble=include_ensemble,
                )
            )
        except Exception as exc:
            ranked.append({"instrument": symbol, "error": str(exc)})
    return ranked


def _refresh_symbol_history(symbols: list[str], dry_run: bool = False) -> dict:
    normalized_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    if not normalized_symbols:
        return {
            "requested_symbols": 0,
            "updated_symbols": 0,
            "total_rows": 0,
            "errors": [],
            "window": None,
            "dry_run": dry_run,
            "sample": [],
        }

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=max(int(AUTONOMOUS_HISTORY_LOOKBACK_DAYS), 5))
    updated = []
    errors = []
    total_rows = 0

    for symbol in normalized_symbols:
        try:
            result = load_history(
                symbol,
                str(start_date),
                str(end_date),
                interval="1d",
                persist=not dry_run,
            )
        except Exception as exc:
            errors.append({"symbol": symbol, "error": " ".join(str(exc).split()) or exc.__class__.__name__})
            continue
        if result.get("error"):
            errors.append({"symbol": symbol, "error": result.get("error")})
            continue
        rows = int(result.get("rows", 0) or 0)
        total_rows += rows
        updated.append({
            "symbol": symbol,
            "rows": rows,
            "source": result.get("source"),
        })

    return {
        "requested_symbols": len(normalized_symbols),
        "updated_symbols": len(updated),
        "total_rows": total_rows,
        "errors": errors[:25],
        "window": {
            "start_date": str(start_date),
            "end_date": str(end_date),
        },
        "dry_run": dry_run,
        "sample": updated[:10],
    }


def _review_and_promote(run_id: str | None) -> dict:
    if not run_id:
        return {
            "promoted_run_id": None,
            "review": None,
            "activation": None,
            "error": "No run_id was returned.",
        }

    review = review_model_promotion(run_id)
    if review.get("error"):
        return {
            "promoted_run_id": None,
            "review": review,
            "activation": None,
            "error": review.get("error"),
        }

    if not review.get("approved"):
        return {
            "promoted_run_id": None,
            "review": review,
            "activation": None,
            "error": None,
        }

    promotion = promote_model_run(run_id)
    return {
        "promoted_run_id": run_id if promotion.get("activation") else None,
        "review": review,
        "activation": promotion.get("activation"),
        "error": promotion.get("error"),
    }


def _market_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    universe = resolve_universe_preset(preset, limit=250)
    symbols = _select_symbols_for_cycle(preset, universe.get("symbols", []), min(10, AUTOMATION_SYMBOL_LIMIT))
    start_date, end_date = _analysis_window()
    snapshots = fetch_quote_snapshots(symbols, include_profile=False)
    ranked = _build_ranked_candidates(
        symbols[:8],
        start_date,
        end_date,
        include_dl=True,
        include_ensemble=True,
    )
    watchlists = build_dynamic_watchlists(preset=preset)
    artifacts = [
        {"artifact_type": "watchlists", "artifact_key": preset.lower(), "payload": watchlists},
        {"artifact_type": "market_snapshots", "artifact_key": "latest", "payload": snapshots},
        {"artifact_type": "smart_rankings", "artifact_key": "top_candidates", "payload": ranked},
    ]
    return (
        f"market_cycle symbols={len(symbols)} failed_snapshots={snapshots.get('failed_symbols', 0)} dry_run={dry_run}",
        artifacts,
    )


def _alert_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    universe = resolve_universe_preset(preset, limit=250)
    alert_symbols = _select_symbols_for_cycle(preset, universe.get("symbols", []), AUTOMATION_ALERT_SYMBOL_LIMIT)
    alerts = generate_advanced_alerts(alert_symbols, persist=not dry_run)
    return (
        f"generated_alerts={alerts.get('count', 0)} symbols={len(alert_symbols)} "
        f"failed_symbols={alerts.get('failed_symbols', 0)} dry_run={dry_run}",
        [
        {"artifact_type": "alerts", "artifact_key": "latest", "payload": alerts},
        ],
    )


def _breadth_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    breadth = compute_market_breadth(preset=preset)
    sectors = compute_sector_rotation()
    return (
        f"breadth_sample={breadth.get('sample_size', 0)} failed_symbols={breadth.get('failed_symbols', 0)} dry_run={dry_run}",
        [
        {"artifact_type": "breadth", "artifact_key": preset.lower(), "payload": breadth},
        {"artifact_type": "sector_rotation", "artifact_key": "sectors", "payload": sectors},
        ],
    )


def _retrain_cycle(dry_run: bool = False) -> tuple[str, list[dict]]:
    if not ENABLE_AUTO_RETRAIN:
        return "auto retraining is disabled by configuration", [
            {"artifact_type": "retrain_status", "artifact_key": "disabled", "payload": {"enabled": False}},
        ]

    if dry_run:
        return "dry run only, no retraining executed", [
            {"artifact_type": "retrain_status", "artifact_key": "dry_run", "payload": {"enabled": True, "dry_run": True}},
        ]

    training_guard = _training_overlap_guard()
    if training_guard is not None:
        return "retraining skipped because the continuous learning worker is already active", [
            {"artifact_type": "retrain_status", "artifact_key": "guarded", "payload": training_guard},
        ]

    start_date, end_date = _training_window()
    ml_result = train_ml_models(
        symbols=DEFAULT_SAMPLE_SYMBOLS,
        start_date=start_date,
        end_date=end_date,
        set_active=False,
    )
    promotion = None
    if ml_result.get("run_id"):
        promotion = _review_and_promote(ml_result["run_id"])
    return f"ml_retrain_status={ml_result.get('status', ml_result.get('error', 'unknown'))}", [
        {"artifact_type": "retrain_result", "artifact_key": "ml", "payload": ml_result},
        {"artifact_type": "promotion_review", "artifact_key": "ml", "payload": promotion},
    ]


def _autonomous_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    universe_refresh = {
        "status": "skipped",
        "enabled": bool(AUTONOMOUS_REFRESH_UNIVERSE),
    }
    if AUTONOMOUS_REFRESH_UNIVERSE:
        try:
            universe_refresh = refresh_market_universe(force=False)
            universe_refresh["enabled"] = True
        except Exception as exc:
            universe_refresh = {
                "status": "error",
                "enabled": True,
                "error": str(exc),
            }

    universe = resolve_universe_preset(preset, limit=250)

    analysis_symbols = _select_symbols_for_cycle(
        preset,
        universe.get("symbols", []),
        max(int(AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT or 0), 1),
    )
    training_symbols = _select_symbols_for_cycle(
        preset,
        universe.get("symbols", []),
        max(int(AUTONOMOUS_TRAIN_SYMBOL_LIMIT or 0), 1),
    )
    if not training_symbols:
        training_symbols = list(DEFAULT_SAMPLE_SYMBOLS)

    history_refresh = _refresh_symbol_history(training_symbols, dry_run=dry_run)
    analysis_start_date, analysis_end_date = _analysis_window()
    train_start_date, train_end_date = _training_window()

    snapshots = fetch_quote_snapshots(analysis_symbols, include_profile=False)
    ranked = _build_ranked_candidates(
        analysis_symbols,
        analysis_start_date,
        analysis_end_date,
        include_dl=AUTONOMOUS_INCLUDE_DL,
        include_ensemble=True,
    )
    watchlists = build_dynamic_watchlists(preset=preset, limit=max(len(analysis_symbols), AUTOMATION_SYMBOL_LIMIT))
    breadth = compute_market_breadth(preset=preset)
    sectors = compute_sector_rotation()
    alerts = generate_advanced_alerts(analysis_symbols, persist=not dry_run)

    ml_training = {
        "status": "skipped",
        "reason": "Auto retraining is disabled.",
    }
    ml_promotion = {
        "promoted_run_id": None,
        "review": None,
        "activation": None,
        "error": None,
    }
    dl_training = {
        "status": "skipped",
        "reason": "DL training is disabled for the autonomous cycle.",
    }
    dl_promotion = {
        "promoted_run_id": None,
        "review": None,
        "activation": None,
        "error": None,
    }
    training_guard = None

    if dry_run:
        ml_training = {
            "status": "dry_run",
            "symbols": training_symbols,
            "start_date": train_start_date,
            "end_date": train_end_date,
        }
        if AUTONOMOUS_INCLUDE_DL:
            dl_training = {
                "status": "dry_run",
                "symbols": training_symbols,
                "start_date": train_start_date,
                "end_date": train_end_date,
            }
    elif ENABLE_AUTO_RETRAIN:
        training_guard = _training_overlap_guard()
        if training_guard is not None:
            ml_training = dict(training_guard)
            ml_promotion = {
                "promoted_run_id": None,
                "review": None,
                "activation": None,
                "error": training_guard["reason"],
            }
            if AUTONOMOUS_INCLUDE_DL:
                dl_training = dict(training_guard)
                dl_promotion = {
                    "promoted_run_id": None,
                    "review": None,
                    "activation": None,
                    "error": training_guard["reason"],
                }
        else:
            ml_training = train_ml_models(
                symbols=training_symbols,
                start_date=train_start_date,
                end_date=train_end_date,
                set_active=False,
            )
            ml_promotion = _review_and_promote(ml_training.get("run_id"))

            if AUTONOMOUS_INCLUDE_DL:
                dl_training = train_dl_models(
                    symbols=training_symbols,
                    start_date=train_start_date,
                    end_date=train_end_date,
                    set_active=False,
                )
                dl_promotion = _review_and_promote(dl_training.get("run_id"))

    top_candidates = [
        {
            "instrument": row.get("instrument"),
            "signal": row.get("smart_signal") or row.get("enhanced_signal") or row.get("signal"),
            "confidence": row.get("smart_confidence", row.get("confidence")),
            "setup_type": row.get("setup_type"),
        }
        for row in ranked
        if not row.get("error")
    ][:5]

    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "preset": preset,
        "dry_run": dry_run,
        "analysis_window": {
            "start_date": analysis_start_date,
            "end_date": analysis_end_date,
        },
        "training_window": {
            "start_date": train_start_date,
            "end_date": train_end_date,
        },
        "universe_refresh": universe_refresh,
        "universe": {
            "preset": universe.get("preset"),
            "matched_count": universe.get("matched_count"),
            "analysis_symbols": analysis_symbols,
            "training_symbols": training_symbols,
        },
        "history_refresh": history_refresh,
        "alerts_count": alerts.get("count", 0),
        "breadth_ratio": breadth.get("breadth_ratio"),
        "top_candidates": top_candidates,
        "training": {
            "auto_retrain_enabled": ENABLE_AUTO_RETRAIN,
            "include_dl": AUTONOMOUS_INCLUDE_DL,
            "guardrail": training_guard,
            "ml": ml_training,
            "ml_promotion": ml_promotion,
            "dl": dl_training,
            "dl_promotion": dl_promotion,
        },
    }

    artifacts = [
        {"artifact_type": "history_refresh", "artifact_key": preset.lower(), "payload": history_refresh},
        {"artifact_type": "market_snapshots", "artifact_key": "autonomous_latest", "payload": snapshots},
        {"artifact_type": "smart_rankings", "artifact_key": "autonomous_top_candidates", "payload": ranked},
        {"artifact_type": "watchlists", "artifact_key": f"{preset.lower()}_autonomous", "payload": watchlists},
        {"artifact_type": "alerts", "artifact_key": "autonomous_latest", "payload": alerts},
        {"artifact_type": "breadth", "artifact_key": f"{preset.lower()}_autonomous", "payload": breadth},
        {"artifact_type": "sector_rotation", "artifact_key": "autonomous_sectors", "payload": sectors},
        {"artifact_type": "retrain_result", "artifact_key": "ml", "payload": ml_training},
        {"artifact_type": "promotion_review", "artifact_key": "ml", "payload": ml_promotion},
    ]
    if AUTONOMOUS_INCLUDE_DL:
        artifacts.extend([
            {"artifact_type": "retrain_result", "artifact_key": "dl", "payload": dl_training},
            {"artifact_type": "promotion_review", "artifact_key": "dl", "payload": dl_promotion},
        ])
    if training_guard is not None:
        artifacts.append({
            "artifact_type": "training_guardrail",
            "artifact_key": "continuous_learning_active",
            "payload": training_guard,
        })
    artifacts.append({
        "artifact_type": "autonomous_summary",
        "artifact_key": _utc_today_iso(),
        "payload": summary,
    })

    detail = (
        f"autonomous_cycle analyzed={len(analysis_symbols)} trained={len(training_symbols)} "
        f"history_symbols={history_refresh.get('updated_symbols', 0)} "
        f"history_errors={len(history_refresh.get('errors', []))} "
        f"alert_failures={alerts.get('failed_symbols', 0)} dry_run={dry_run}"
    )
    if training_guard is not None:
        detail = f"{detail} training_guarded=true"
    return detail, artifacts


def _daily_summary(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    breadth = compute_market_breadth(preset=preset)
    watchlists = build_dynamic_watchlists(preset=preset)
    portfolio = get_portfolio_exposure()
    broker = get_broker_summary()
    alerts = list_alert_history(limit=10)
    journal = list_trade_journal_entries(limit=10)
    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "breadth": breadth,
        "watchlists": watchlists,
        "portfolio": portfolio.get("summary", {}),
        "broker": {
            "provider": broker.get("provider"),
            "connected": broker.get("connected"),
            "mode": broker.get("mode"),
            "totals": broker.get("totals", {}),
            "account": broker.get("account"),
        },
        "alerts": alerts.get("items", []),
        "journal": journal.get("classification_counts", {}),
    }
    return f"daily_summary alerts={len(alerts.get('items', []))} dry_run={dry_run}", [
        {"artifact_type": "daily_summary", "artifact_key": datetime.utcnow().date().isoformat(), "payload": summary},
    ]


def run_automation_job(job_name: str, dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> dict:
    normalized = str(job_name or "").strip().lower()
    started_at = datetime.utcnow()
    handlers = {
        "market_cycle": lambda: _market_cycle(dry_run=dry_run, preset=preset),
        "alert_cycle": lambda: _alert_cycle(dry_run=dry_run, preset=preset),
        "breadth_cycle": lambda: _breadth_cycle(dry_run=dry_run, preset=preset),
        "retrain_cycle": lambda: _retrain_cycle(dry_run=dry_run),
        "autonomous_cycle": lambda: _autonomous_cycle(dry_run=dry_run, preset=preset),
        "daily_summary": lambda: _daily_summary(dry_run=dry_run, preset=preset),
    }
    handler = handlers.get(normalized)
    if handler is None:
        return {"error": f"Unsupported automation job: {job_name}"}

    started_perf = perf_counter()
    log_event(logger, logging.INFO, "automation.run.started", job_name=normalized, dry_run=dry_run, preset=preset)
    try:
        detail, artifacts = handler()
        result = _record_run(normalized, "completed", started_at, dry_run, detail, artifacts)
        result["duration_seconds"] = round(perf_counter() - started_perf, 4)
        log_event(logger, logging.INFO, "automation.run.completed", job_name=normalized, dry_run=dry_run, duration_seconds=result["duration_seconds"], artifacts=len(artifacts))
        return result
    except Exception as exc:
        result = _record_run(normalized, "error", started_at, dry_run, str(exc), [])
        result["duration_seconds"] = round(perf_counter() - started_perf, 4)
        result["error"] = str(exc)
        log_event(logger, logging.ERROR, "automation.run.failed", job_name=normalized, dry_run=dry_run, duration_seconds=result["duration_seconds"], error=str(exc))
        return result


def get_automation_status(limit: int = 20) -> dict:
    limit = max(1, min(int(limit or 20), 100))
    with session_scope() as session:
        rows = (
            session.query(AutomationRun)
            .order_by(AutomationRun.started_at.desc())
            .limit(limit)
            .all()
        )
        items = [
            {
                "run_id": row.run_id,
                "job_name": row.job_name,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "duration_seconds": row.duration_seconds,
                "dry_run": bool(row.dry_run),
                "detail": row.detail,
                "artifacts_count": row.artifacts_count,
            }
            for row in rows
        ]
        artifacts = (
            session.query(AutomationArtifact)
            .order_by(AutomationArtifact.created_at.desc())
            .limit(limit)
            .all()
        )
        latest_artifacts = [
            {
                "run_id": row.run_id,
                "job_name": row.job_name,
                "artifact_type": row.artifact_type,
                "artifact_key": row.artifact_key,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "payload": loads_json(row.payload_json),
            }
            for row in artifacts
        ]

    return {
        "jobs": [{"job_name": key, "label": value} for key, value in JOB_NAMES.items()],
        "recent_runs": items,
        "latest_artifacts": latest_artifacts,
        "auto_retrain_enabled": ENABLE_AUTO_RETRAIN,
        "autonomous_cycle_enabled": ENABLE_AUTONOMOUS_CYCLE,
        "autonomous_analysis_symbol_limit": AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT,
        "autonomous_train_symbol_limit": AUTONOMOUS_TRAIN_SYMBOL_LIMIT,
        "autonomous_include_dl": AUTONOMOUS_INCLUDE_DL,
    }
