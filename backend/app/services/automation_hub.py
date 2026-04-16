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
    AUTO_TRADING_ENABLED,
    AUTO_TRADING_QUANTITY,
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
    "auto_trading_cycle": "Auto Trading Cycle",
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


def _rotate_symbol_batch(symbols: list[str], desired_count: int) -> tuple[list[str], dict]:
    desired_count = max(int(desired_count or 0), 1)
    cleaned = [str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()]
    if not cleaned:
        return [], {"offset": 0, "next_offset": 0, "pool_size": 0, "batch_size": desired_count}

    from backend.app.services.runtime_settings import get_runtime_setting_value, set_runtime_setting_value

    pool_size = len(cleaned)
    try:
        offset = int(get_runtime_setting_value("auto_trading.rotation_cursor") or 0) % pool_size
    except Exception:
        offset = 0

    batch: list[str] = []
    for index in range(min(desired_count, pool_size)):
        batch.append(cleaned[(offset + index) % pool_size])

    next_offset = (offset + len(batch)) % pool_size
    try:
        set_runtime_setting_value("auto_trading.rotation_cursor", next_offset)
    except Exception:
        pass

    return batch, {
        "offset": offset,
        "next_offset": next_offset,
        "pool_size": pool_size,
        "batch_size": len(batch),
    }


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



def _auto_trading_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    """Auto-trading cycle: scan all symbols, generate signals, auto-execute BUY orders.

    Paper-mode friendly: if MARKET_AI_PAPER_TRADING_24_7=1 OR Alpaca is not properly
    configured, we run the cycle against the INTERNAL paper_positions table with no
    market-hours restriction and no broker dependency. This lets the bot trade
    continuously for simulation/learning.
    """
    import os
    from backend.app.services.runtime_settings import get_auto_trading_config

    paper_24_7 = str(os.environ.get("MARKET_AI_PAPER_TRADING_24_7", "1")).strip() in {"1", "true", "True", "yes"}

    # Check runtime settings
    auto_config = get_auto_trading_config()
    # In paper-only mode we only need auto_trading.enabled — Alpaca is irrelevant for
    # internal paper positions. This unblocks trading when broker creds are missing/invalid.
    paper_ready = bool(auto_config["auto_trading_enabled"])
    effective_ready = paper_ready if paper_24_7 else auto_config["ready"]

    if not effective_ready:
        return (
            f"auto_trading_cycle skipped: not ready (auto_trading={auto_config['auto_trading_enabled']}, "
            f"order_sub={auto_config['order_submission_enabled']}, alpaca_configured={auto_config['alpaca_configured']}, paper_24_7={paper_24_7})",
            [{"artifact_type": "auto_trading_status", "artifact_key": "skipped", "payload": {**auto_config, "paper_24_7": paper_24_7}}],
        )

    if dry_run:
        return (
            "auto_trading_cycle dry_run=True",
            [{"artifact_type": "auto_trading_status", "artifact_key": "dry_run", "payload": {"dry_run": True, **auto_config}}],
        )

    # Market-hours check: bypass when paper_24_7 is enabled (pure internal simulation).
    market_open = _is_us_market_open() if not paper_24_7 else True
    if not market_open:
        return (
            "auto_trading_cycle skipped: market is closed",
            [{"artifact_type": "auto_trading_status", "artifact_key": "market_closed", "payload": {"market_open": False}}],
        )

    # Cap symbols per cycle so the schedule doesn't overlap with itself.
    # Each full ML analysis takes ~2 min on a 2-vCPU box, so for a 5-min cycle we
    # typically pick 2 symbols (see MARKET_AI_AUTO_TRADING_SYMBOL_LIMIT in .env).
    try:
        symbol_limit = int(os.environ.get("MARKET_AI_AUTO_TRADING_SYMBOL_LIMIT", "10"))
    except Exception:
        symbol_limit = 10
    symbol_limit = max(1, min(symbol_limit, 500))
    full_portfolio_mode = str(os.environ.get("MARKET_AI_AUTO_TRADING_USE_FULL_PORTFOLIO", "0")).strip().lower() in {"1", "true", "yes", "on"}
    universe_preset = str(auto_config.get("universe_preset") or preset or AUTOMATION_DEFAULT_PRESET).strip().upper()
    use_top_market_cap_rotation = universe_preset == "TOP_500_MARKET_CAP"
    symbols = list(DEFAULT_SAMPLE_SYMBOLS)
    rotation_state = {"offset": 0, "next_offset": 0, "pool_size": len(symbols), "batch_size": 0}
    ranked_universe_symbols: list[str] = []
    if use_top_market_cap_rotation:
        try:
            top_market_cap = resolve_universe_preset("TOP_500_MARKET_CAP", limit=500)
            ranked_universe_symbols = list(top_market_cap.get("symbols") or [])
            rotated_batch, rotation_state = _rotate_symbol_batch(ranked_universe_symbols, symbol_limit)
            if rotated_batch:
                symbols = rotated_batch
        except Exception:
            ranked_universe_symbols = []

    # Rotation: prefer symbols that don't already have an open position so each
    # cycle has a real chance to generate a NEW trade. Reserve one slot for a
    # held name so exit signals still get re-evaluated periodically.
    import random as _random
    try:
        from backend.app.application.execution.service import get_internal_portfolio
        held_payload = get_internal_portfolio(limit=500) or {}
        held_positions = {
            str(pos.get("symbol") or "").upper(): str(pos.get("side") or "").upper()
            for pos in (held_payload.get("items") or [])
            if (pos.get("status") or "").upper() == "OPEN"
        }
        held = set(held_positions.keys())
    except Exception:
        held_positions = {}
        held = set()

    if use_top_market_cap_rotation and ranked_universe_symbols:
        held_pool = [s for s in ranked_universe_symbols if s in held]
        rotation = [s for s in symbols if s not in held]
        if held_pool and held_pool[0] not in rotation:
            rotation = [held_pool[0], *rotation]
        symbols = list(dict.fromkeys(rotation))[:symbol_limit] or list(DEFAULT_SAMPLE_SYMBOLS)[:symbol_limit]
    else:
        unheld = [s for s in symbols if s not in held]
        held_pool = [s for s in symbols if s in held]
        _random.shuffle(unheld)
        _random.shuffle(held_pool)
        if symbol_limit >= 2 and held_pool and unheld:
            rotation = unheld[: symbol_limit - 1] + held_pool[:1]
        else:
            rotation = (unheld + held_pool)[:symbol_limit]
        symbols = rotation[:symbol_limit] or list(DEFAULT_SAMPLE_SYMBOLS)[:symbol_limit]
    candidate_symbols = list(symbols)
    if full_portfolio_mode and not use_top_market_cap_rotation:
        mover_limit = max(symbol_limit * 4, 12)
        try:
            local_candidates = []
            for candidate in _preferred_local_symbols(preset):
                normalized = str(candidate or "").upper()
                if not normalized.isalpha():
                    continue
                if len(normalized) > 5:
                    continue
                if normalized.endswith(("W", "U", "R")):
                    continue
                local_candidates.append(normalized)
                if len(local_candidates) >= 80:
                    break
            snapshot_symbols = local_candidates or list(DEFAULT_SAMPLE_SYMBOLS)
            mover_snapshots = fetch_quote_snapshots(snapshot_symbols, include_profile=False)
            mover_items = [
                item
                for item in (mover_snapshots or {}).get("items", [])
                if float(item.get("last_price") or item.get("price") or 0.0) >= 5.0
            ]
            mover_symbols = [
                str(item.get("symbol") or "").upper()
                for item in sorted(
                    mover_items,
                    key=lambda entry: abs(float(entry.get("change_pct") or 0.0)),
                    reverse=True,
                )
                if str(item.get("symbol") or "").strip()
            ][:mover_limit]
            candidate_symbols = list(dict.fromkeys(held_pool + mover_symbols))
        except Exception:
            candidate_symbols = list(dict.fromkeys(held_pool + list(DEFAULT_SAMPLE_SYMBOLS)[:mover_limit]))
    elif use_top_market_cap_rotation:
        candidate_symbols = list(symbols)

    # Run signal refresh with auto-execute.
    # Use a shorter analysis window for auto-trading so each symbol finishes fast
    # enough that cycles don't pile up behind the 5-min schedule.
    from backend.app.application.execution.service import refresh_signals
    from datetime import datetime as _dt, timedelta as _td

    try:
        lookback_days = int(os.environ.get("MARKET_AI_AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS", "0"))
    except Exception:
        lookback_days = 0

    if lookback_days > 0:
        end_date = _utc_today_iso()
        start_date = (_dt.utcnow() - _td(days=lookback_days)).strftime("%Y-%m-%d")
    else:
        start_date, end_date = _analysis_window()

    # --- dynamic position sizing: aim for NOTIONAL_PER_TRADE dollars per symbol.
    # In full-portfolio mode we size from the internal paper wallet cash balance,
    # which makes the next entry consume all currently available cash.
    # Fetch quotes up-front (cheap) to size each order in shares. Falls back to the
    # flat AUTO_TRADING_QUANTITY when a quote is unavailable.
    fallback_qty = max(AUTO_TRADING_QUANTITY, 1.0)
    try:
        notional_per_trade = float(os.environ.get("MARKET_AI_AUTO_TRADING_NOTIONAL_PER_TRADE", "0") or 0.0)
    except Exception:
        notional_per_trade = 0.0
    portfolio_cash_balance = 0.0
    portfolio_equity = 0.0
    try:
        from backend.app.application.execution.service import get_internal_portfolio

        portfolio_payload = get_internal_portfolio(limit=500) or {}
        portfolio_summary = portfolio_payload.get("summary") or {}
        portfolio_cash_balance = float(portfolio_summary.get("cash_balance") or 0.0)
        portfolio_equity = float(portfolio_summary.get("total_equity") or 0.0)
    except Exception:
        portfolio_payload = {}
        portfolio_summary = {}

    if full_portfolio_mode:
        notional_per_trade = max(portfolio_cash_balance, 0.0)
        if notional_per_trade <= 0:
            notional_per_trade = max(portfolio_equity, 0.0)

    price_lookup: dict[str, float] = {}
    quote_symbols = list(
        dict.fromkeys(candidate_symbols if full_portfolio_mode and candidate_symbols else symbols)
    )
    if notional_per_trade > 0 and quote_symbols:
        try:
            from backend.app.services.market_data import fetch_quote_snapshots
            snap = fetch_quote_snapshots(quote_symbols, include_profile=False)
            for item in (snap or {}).get("items", []):
                sym = str(item.get("symbol") or "").upper()
                px = float(item.get("last_price") or item.get("price") or 0.0)
                if sym and px > 0:
                    price_lookup[sym] = px
        except Exception:
            price_lookup = {}

    def _compute_qty(symbol: str, budget: float | None = None) -> float:
        effective_budget = float(notional_per_trade if budget is None else budget or 0.0)
        if effective_budget <= 0:
            return fallback_qty
        px = price_lookup.get(symbol.upper(), 0.0)
        if px <= 0:
            return fallback_qty
        shares = max(int(effective_budget // px), 1)
        return float(shares)

    # Loop per symbol when dynamic sizing is active so each order can carry its
    # own share count. Small N here (typically 2) keeps this practical.
    aggregate_items: list[dict] = []
    last_correlation: str | None = None
    allocated_quantities: dict[str, float] = {}
    selected_execution_candidates: list[dict] = []
    try:
        if notional_per_trade > 0:
            if full_portfolio_mode and candidate_symbols:
                preview_candidates: list[dict] = []
                actionable_candidates: list[dict] = []
                for index, sym in enumerate(candidate_symbols):
                    try:
                        preview_result = build_smart_analysis(sym, start_date, end_date, include_dl=True, include_ensemble=True)
                        if "error" in preview_result:
                            preview_candidates.append({"symbol": sym, "error": preview_result.get("error")})
                            continue
                        signal_view = extract_signal_view(preview_result, mode="classic")
                        signal_value = str(signal_view.get("signal") or "HOLD").upper()
                        current_side = held_positions.get(sym.upper())
                        desired_side = "LONG" if signal_value == "BUY" else "SHORT" if signal_value == "SELL" else None
                        preview_entry = {
                            "symbol": sym,
                            "signal": signal_value,
                            "confidence": float(signal_view.get("confidence") or 0.0),
                            "price": float(signal_view.get("price") or price_lookup.get(sym.upper()) or 0.0),
                            "current_side": current_side,
                            "result": preview_result,
                        }
                        preview_candidates.append(preview_entry)
                        if desired_side and current_side != desired_side and preview_entry["price"] >= 5.0:
                            actionable_candidates.append(preview_entry)
                    except Exception as exc:
                        preview_candidates.append({"symbol": sym, "error": str(exc)})
                actionable_candidates = [
                    item for item in sorted(actionable_candidates, key=lambda entry: float(entry.get("confidence") or 0.0), reverse=True)
                    if float(item.get("price") or price_lookup.get(item.get("symbol", "").upper()) or 0.0) > 0
                ]
                if actionable_candidates:
                    selected_candidates = actionable_candidates[:symbol_limit]
                    selected_execution_candidates = list(selected_candidates)
                    symbols = [item["symbol"] for item in selected_candidates]
                    budget_per_symbol = max(float(notional_per_trade) * 0.995 / len(selected_candidates), 0.0)
                    for item in selected_candidates:
                        qty = _compute_qty(item["symbol"], budget=budget_per_symbol)
                        if qty > 0:
                            allocated_quantities[item["symbol"].upper()] = qty
            if not full_portfolio_mode and symbols and not allocated_quantities:
                for sym in symbols:
                    qty = _compute_qty(sym, budget=float(notional_per_trade))
                    if qty > 0:
                        allocated_quantities[sym.upper()] = qty
            if full_portfolio_mode and symbols and not allocated_quantities:
                new_entry_symbols = [sym for sym in symbols if sym.upper() not in held_positions] or list(symbols)
                budget_per_symbol = max(float(notional_per_trade) * 0.995 / len(new_entry_symbols), 0.0)
                for sym in new_entry_symbols:
                    qty = _compute_qty(sym, budget=budget_per_symbol)
                    if qty > 0:
                        allocated_quantities[sym.upper()] = qty
            if full_portfolio_mode and selected_execution_candidates:
                from backend.app.application.execution.service import (
                    _apply_trade_intent,
                    _build_quote_lookup,
                    _build_signal_snapshot,
                    _build_trade_intents,
                    _record_signal_alerts,
                    get_alert_history,
                    get_internal_portfolio,
                    get_signal_history,
                )
                from backend.app.domain.execution.contracts import ExecutionEventRecord, PositionState, SignalRecord
                from backend.app.repositories.execution import ExecutionRepository

                last_correlation = f"paper-refresh-{uuid4().hex[:12]}"
                quote_lookup = _build_quote_lookup(symbols)
                with session_scope() as session:
                    repo = ExecutionRepository(session)
                    for item in selected_execution_candidates:
                        sym = item["symbol"]
                        signal_snapshot = _build_signal_snapshot(
                            sym,
                            "classic",
                            item.get("result") or build_smart_analysis(sym, start_date, end_date, include_dl=True, include_ensemble=True),
                            start_date,
                            end_date,
                            quote_lookup=quote_lookup,
                        )
                        previous_signal = repo.latest_signal(sym, "classic")
                        repo.append_signal(
                            SignalRecord(
                                symbol=sym,
                                strategy_mode="classic",
                                signal=signal_snapshot.signal,
                                confidence=signal_snapshot.confidence,
                                price=signal_snapshot.price,
                                reasoning=signal_snapshot.reasoning,
                                payload=signal_snapshot.analysis_payload,
                            )
                        )
                        _record_signal_alerts(repo, "classic", signal_snapshot, previous_signal)
                        repo.append_audit_event(
                            ExecutionEventRecord(
                                event_type="signal_recorded",
                                symbol=sym,
                                strategy_mode="classic",
                                correlation_id=last_correlation,
                                payload=signal_snapshot.model_dump(),
                            )
                        )
                        current_row = repo.get_open_position_row(sym, "classic")
                        current_position = None if current_row is None else PositionState(
                            id=current_row.id,
                            symbol=current_row.symbol,
                            strategy_mode=current_row.strategy_mode,
                            side=current_row.side,
                            quantity=current_row.quantity,
                            avg_entry_price=current_row.avg_entry_price,
                            current_price=current_row.current_price,
                            market_value=current_row.market_value or 0.0,
                            unrealized_pnl=current_row.unrealized_pnl or 0.0,
                            realized_pnl=current_row.realized_pnl or 0.0,
                            status=current_row.status,
                            opened_at=current_row.opened_at,
                            updated_at=current_row.updated_at,
                        )
                        qty = allocated_quantities.get(sym.upper(), fallback_qty)
                        intents = _build_trade_intents(current_position, signal_snapshot, qty)
                        for intent in intents:
                            _apply_trade_intent(repo, current_row, intent, correlation_id=last_correlation)
                            if intent.intent.startswith("CLOSE"):
                                current_row = None
                        aggregate_items.append(
                            {
                                "symbol": sym,
                                "strategy_mode": "classic",
                                "signal": signal_snapshot.signal,
                                "confidence": signal_snapshot.confidence,
                                "price": signal_snapshot.price,
                                "reasoning": signal_snapshot.reasoning,
                            }
                        )
                    repo.append_audit_event(
                        ExecutionEventRecord(
                            event_type="refresh_completed",
                            correlation_id=last_correlation,
                            payload={"symbols": symbols, "mode": "classic", "results": len(aggregate_items)},
                        )
                    )
                result = {
                    "items": aggregate_items,
                    "correlation_id": last_correlation,
                    "portfolio": get_internal_portfolio(limit=500),
                    "alerts": get_alert_history(limit=20),
                    "signals": get_signal_history(limit=20),
                }
            else:
                result = refresh_signals(
                    symbols=symbols,
                    mode="classic",
                    start_date=start_date,
                    end_date=end_date,
                    auto_execute=True,
                    quantity=fallback_qty,
                    quantity_map=allocated_quantities,
                )
                aggregate_items = list(result.get("items", []))
                last_correlation = result.get("correlation_id") or last_correlation
            quantity = fallback_qty  # reported default; per-symbol used above
        else:
            result = refresh_signals(
                symbols=symbols,
                mode="classic",
                start_date=start_date,
                end_date=end_date,
                auto_execute=True,
                quantity=fallback_qty,
            )
            quantity = fallback_qty
    except Exception as exc:
        return (
            f"auto_trading_cycle failed: {exc}",
            [{"artifact_type": "auto_trading_error", "artifact_key": "execution_failed", "payload": {"error": str(exc)}}],
        )

    # Summarize results
    items = result.get("items", [])
    buy_signals = [i for i in items if i.get("signal") == "BUY"]
    sell_signals = [i for i in items if i.get("signal") == "SELL"]
    hold_signals = [i for i in items if i.get("signal") == "HOLD"]
    errors = [i for i in items if i.get("error")]

    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "universe_preset": universe_preset,
        "use_top_market_cap_rotation": use_top_market_cap_rotation,
        "symbols_scanned": len(symbols),
        "buy_signals": len(buy_signals),
        "sell_signals": len(sell_signals),
        "hold_signals": len(hold_signals),
        "errors": len(errors),
        "auto_executed": True,
        "quantity_per_trade": quantity,
        "full_portfolio_mode": full_portfolio_mode,
        "notional_per_trade": round(float(notional_per_trade or 0.0), 4),
        "portfolio_cash_balance": round(float(portfolio_cash_balance or 0.0), 4),
        "allocated_quantities": allocated_quantities,
        "correlation_id": result.get("correlation_id"),
        "rotation": rotation_state,
        "rotation_pool_size": len(ranked_universe_symbols),
        "top_buys": [
            {"symbol": i["symbol"], "confidence": i.get("confidence", 0), "price": i.get("price", 0)}
            for i in sorted(buy_signals, key=lambda x: x.get("confidence", 0), reverse=True)[:5]
        ],
        "portfolio": result.get("portfolio", {}),
    }

    # Send Telegram notification
    try:
        from backend.app.services.trade_notifier import notify_auto_trading_summary
        notify_auto_trading_summary(
            symbols_scanned=len(symbols),
            buy_count=len(buy_signals),
            sell_count=len(sell_signals),
            hold_count=len(hold_signals),
            errors=len(errors),
            top_buys=summary.get("top_buys", []),
        )
    except Exception:
        pass

    detail = (
        f"auto_trading_cycle preset={universe_preset} scanned={len(symbols)} buys={len(buy_signals)} "
        f"sells={len(sell_signals)} holds={len(hold_signals)} errors={len(errors)} "
        f"qty={quantity}"
    )

    artifacts = [
        {"artifact_type": "auto_trading_summary", "artifact_key": _utc_today_iso(), "payload": summary},
        {"artifact_type": "auto_trading_signals", "artifact_key": "latest", "payload": items},
        {"artifact_type": "auto_trading_rotation", "artifact_key": universe_preset.lower(), "payload": rotation_state},
    ]

    return detail, artifacts


def _is_us_market_open() -> bool:
    """Check if the US stock market is currently open (9:30 AM - 4:00 PM ET, weekdays)."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    now_et = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))

    # Weekend check
    if now_et.weekday() >= 5:
        return False

    # Market hours: 9:30 AM to 4:00 PM ET
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now_et <= market_close


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
        "auto_trading_cycle": lambda: _auto_trading_cycle(dry_run=dry_run, preset=preset),
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
