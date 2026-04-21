"""Cycle handlers for automation jobs.

Each handler returns `(detail, artifacts)` and keeps existing payload contracts
used by scheduler/runtime surfaces.
"""

from __future__ import annotations

from datetime import datetime

from backend.app.application.alerts.service import list_alert_history
from backend.app.application.broker.service import get_broker_summary
from backend.app.application.model_lifecycle.service import train_dl_models, train_ml_models
from backend.app.application.portfolio.service import get_portfolio_exposure
from backend.app.config import (
    AUTOMATION_ALERT_SYMBOL_LIMIT,
    AUTOMATION_DEFAULT_PRESET,
    AUTOMATION_SYMBOL_LIMIT,
    AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT,
    AUTONOMOUS_INCLUDE_DL,
    AUTONOMOUS_REFRESH_UNIVERSE,
    AUTONOMOUS_TRAIN_SYMBOL_LIMIT,
    DEFAULT_SAMPLE_SYMBOLS,
    ENABLE_AUTO_RETRAIN,
    LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
)
from backend.app.services.advanced_alerts import generate_advanced_alerts
from backend.app.services.automation.common import (
    _analysis_window,
    _build_ranked_candidates,
    _refresh_symbol_history,
    _review_and_promote,
    _select_symbols_for_cycle,
    _training_overlap_guard,
    _training_window,
    _utc_today_iso,
)
from backend.app.services.breadth_engine import compute_market_breadth, compute_sector_rotation
from backend.app.services.market_data import fetch_quote_snapshots
from backend.app.services.market_universe import refresh_market_universe, resolve_universe_preset
from backend.app.services.smart_watchlists import build_dynamic_watchlists
from backend.app.services.trade_journal import list_trade_journal_entries


def _market_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    universe = resolve_universe_preset(preset, limit=250)
    symbols = _select_symbols_for_cycle(preset, universe.get("symbols", []), min(10, AUTOMATION_SYMBOL_LIMIT))
    start_date, end_date = _analysis_window()
    snapshots = fetch_quote_snapshots(symbols, include_profile=False)
    ranked = _build_ranked_candidates(
        symbols[:8],
        start_date,
        end_date,
        include_dl=LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
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
