"""
Continuous Learning Service

This module implements an autonomous market learning loop that runs on a configurable schedule
to continuously evaluate, optimize, and promote trading strategies. The service is organized
into distinct functional areas:

PROCESS MANAGEMENT:
  - Spawning and supervising isolated continuous learning worker processes
  - Coordinating lifecycle: start, pause, resume, shutdown
  - Enforcing mutual exclusion via worker claims and heartbeats

STATE MANAGEMENT:
  - Tracking continuous learning state (running, paused, idle, error)
  - Maintaining worker registration and health signals
  - Persisting state across process restarts

DATA PIPELINE:
  - Refreshing historical market data and current snapshots
  - Resolving the training/evaluation/analysis universes
  - Collecting outcome snapshots from prior trades/positions

LEARNING & OPTIMIZATION:
  - Computing outcome metrics and policy weights
  - Generating candidate strategy variations (blueprints-based)
  - Evaluating candidates on historical backtests
  - Ranking by performance metrics (return, win rate, drawdown, expectancy)

MODEL LIFECYCLE:
  - Training ML/DL models with symbol data over training windows
  - Reviewing promotion requirements and promoting active models
  - Recording model run artifacts

MAIN ORCHESTRATION:
  - run_continuous_learning_loop() — worker process main loop
  - _run_cycle() — single learning iteration (market refresh -> evaluation -> promotion)
  - Coordinated through APScheduler and background process management

PUBLIC API:
  - start_continuous_learning() — trigger a new learning cycle
  - pause_continuous_learning() / resume_continuous_learning() — control flow
  - get_continuous_learning_status() — fetch recent runs and state
  - list_continuous_learning_artifacts() / list_generated_strategy_candidates() — artifact queries
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import UTC, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from backend.app.application.model_lifecycle.service import (
    list_model_runs,
    promote_model_run,
    review_model_promotion,
    train_dl_models,
    train_ml_models,
)
from backend.app.config import (
    AUTOMATION_DEFAULT_PRESET,
    AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT,
    AUTONOMOUS_HISTORY_LOOKBACK_DAYS,
    AUTONOMOUS_INCLUDE_DL,
    AUTONOMOUS_REFRESH_UNIVERSE,
    AUTONOMOUS_TRAIN_SYMBOL_LIMIT,
    CONTINUOUS_LEARNING_CYCLE_SECONDS,
    CONTINUOUS_LEARNING_EVALUATION_SYMBOLS,
    CONTINUOUS_LEARNING_HEARTBEAT_SECONDS,
    CONTINUOUS_LEARNING_MAX_CANDIDATES,
    CONTINUOUS_LEARNING_PAUSE_SECONDS,
    CONTINUOUS_LEARNING_POLICY_LOOKBACK_DAYS,
    CONTINUOUS_LEARNING_ROLE_ALLOWED,
    CONTINUOUS_LEARNING_RUNNER_PYTHON,
    CONTINUOUS_LEARNING_RUNNER_ROLE,
    CONTINUOUS_LEARNING_STALE_SECONDS,
    CONTINUOUS_LEARNING_STARTUP_ENABLED,
    DEFAULT_SAMPLE_SYMBOLS,
    ENABLE_AUTO_RETRAIN,
    ENABLE_CONTINUOUS_LEARNING,
    ROOT_DIR,
    SERVER_ROLE,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models import (
    AnalysisRun,
    ContinuousLearningArtifact,
    ContinuousLearningRun,
    ContinuousLearningState,
    PaperPosition,
    PaperTrade,
    SignalHistory,
    StrategyEvaluationRun,
)
from backend.app.services.market_data import fetch_quote_snapshots, load_history
from backend.app.services.market_universe import refresh_market_universe, resolve_universe_preset
from backend.app.services.process_guardrails import is_process_running
from backend.app.services.signal_runtime import build_smart_analysis
from backend.app.services.storage import dumps_json, loads_json, session_scope
from core.backtest_service import backtest_symbol_enhanced
from core.runtime_paths import CONTINUOUS_LEARNING_ARTIFACTS_DIR, CONTINUOUS_LEARNING_LOGS_DIR, ensure_runtime_directories


ENGINE_KEY = "continuous_learning"
logger = get_logger(__name__)

CANDIDATE_BLUEPRINTS = [
    {
        "name": "factor_quality",
        "family": "factor",
        "description": "Quality-factor bias with balanced confirmation thresholds.",
        "params": {"hold_days": 10, "min_technical_score": 2, "buy_score_threshold": 3, "sell_score_threshold": 4},
    },
    {
        "name": "momentum_acceleration",
        "family": "momentum",
        "description": "Faster momentum capture for stronger directional expansions.",
        "params": {"hold_days": 7, "min_technical_score": 2, "buy_score_threshold": 4, "sell_score_threshold": 4},
    },
    {
        "name": "mean_reversion_swing",
        "family": "mean_reversion",
        "description": "Shorter swing window for oversold and overbought reversions.",
        "params": {"hold_days": 4, "min_technical_score": 2, "buy_score_threshold": 2, "sell_score_threshold": 2},
    },
    {
        "name": "volatility_breakout",
        "family": "volatility",
        "description": "Breakout-focused profile for squeeze and expansion setups.",
        "params": {"hold_days": 6, "min_technical_score": 2, "buy_score_threshold": 4, "sell_score_threshold": 5},
    },
    {
        "name": "hybrid_ml_trend",
        "family": "hybrid_ml",
        "description": "Hybrid candidate that leans on active smart-signal alignment.",
        "params": {"hold_days": 8, "min_technical_score": 2, "buy_score_threshold": 3, "sell_score_threshold": 4},
    },
    {
        "name": "ensemble_policy",
        "family": "ensemble",
        "description": "More selective policy profile tuned for ensemble confirmation.",
        "params": {"hold_days": 12, "min_technical_score": 3, "buy_score_threshold": 4, "sell_score_threshold": 4},
    },
]


# ============================================================================
# SECTION: UTILITIES
# ============================================================================
# Low-level helper functions for common operations.

def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _score_formula(*, total_return_pct: float = 0.0, win_rate_pct: float = 0.0, max_drawdown_pct: float = 0.0, expectancy_pct: float = 0.0) -> float:
    return round(
        (total_return_pct * 0.35)
        + (win_rate_pct * 0.25)
        + (expectancy_pct * 12.0)
        - (max_drawdown_pct * 0.25),
        3,
    )


def _continuous_log_path() -> Path:
    ensure_runtime_directories()
    CONTINUOUS_LEARNING_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return CONTINUOUS_LEARNING_LOGS_DIR / "continuous_learning.log"


def _candidate_artifact_dir(run_id: str) -> Path:
    ensure_runtime_directories()
    directory = CONTINUOUS_LEARNING_ARTIFACTS_DIR / run_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_json(path: Path, payload: dict | list) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(path)


# ============================================================================
# SECTION: SERIALIZATION
# ============================================================================
# Convert database models to JSON-serializable dictionaries for API responses.

def _serialize_state(row: ContinuousLearningState) -> dict:
    return {
        "engine_key": row.engine_key,
        "desired_state": row.desired_state,
        "runtime_status": row.runtime_status,
        "active_stage": row.active_stage,
        "worker_id": row.worker_id,
        "active_pid": row.active_pid,
        "current_run_id": row.current_run_id,
        "last_started_at": row.last_started_at.isoformat() if row.last_started_at else None,
        "last_heartbeat_at": row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None,
        "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
        "last_cycle_started_at": row.last_cycle_started_at.isoformat() if row.last_cycle_started_at else None,
        "last_cycle_completed_at": row.last_cycle_completed_at.isoformat() if row.last_cycle_completed_at else None,
        "next_cycle_at": row.next_cycle_at.isoformat() if row.next_cycle_at else None,
        "current_model_version": row.current_model_version,
        "best_strategy_name": row.best_strategy_name,
        "best_strategy_run_id": row.best_strategy_run_id,
        "latest_metrics": loads_json(row.latest_metrics_json, default={}),
        "latest_artifact_path": row.latest_artifact_path,
        "last_failure_reason": row.last_failure_reason,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_run(row: ContinuousLearningRun) -> dict:
    return {
        "run_id": row.run_id,
        "status": row.status,
        "stage": row.stage,
        "cycle_type": row.cycle_type,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "duration_seconds": row.duration_seconds,
        "summary": loads_json(row.summary_json, default={}),
        "metrics": loads_json(row.metrics_json, default={}),
        "error_message": row.error_message,
    }


def _serialize_artifact(row: ContinuousLearningArtifact) -> dict:
    return {
        "run_id": row.run_id,
        "artifact_type": row.artifact_type,
        "artifact_key": row.artifact_key,
        "payload": loads_json(row.payload_json, default={}),
        "file_path": row.file_path,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ============================================================================
# SECTION: STATE MANAGEMENT
# ============================================================================
# Retrieve and update continuous learning state in the database.

def _get_or_create_state(session) -> ContinuousLearningState:
    state = (
        session.query(ContinuousLearningState)
        .filter(ContinuousLearningState.engine_key == ENGINE_KEY)
        .first()
    )
    if state is None:
        state = ContinuousLearningState(
            engine_key=ENGINE_KEY,
            desired_state="running" if ENABLE_CONTINUOUS_LEARNING else "paused",
            runtime_status="idle",
            active_stage="idle",
            next_cycle_at=_utcnow() if ENABLE_CONTINUOUS_LEARNING else None,
        )
        session.add(state)
        session.flush()
    return state


def _heartbeat_is_fresh(state: ContinuousLearningState | None, now: datetime | None = None) -> bool:
    if state is None or state.last_heartbeat_at is None:
        return False
    reference = _utcnow() if now is None else now
    stale_window = max(CONTINUOUS_LEARNING_STALE_SECONDS, CONTINUOUS_LEARNING_HEARTBEAT_SECONDS * 2, 60)
    return state.last_heartbeat_at >= reference - timedelta(seconds=stale_window)


def _startup_is_fresh(state: ContinuousLearningState | None, now: datetime | None = None) -> bool:
    if state is None or state.last_started_at is None or str(state.runtime_status or "").lower() != "starting":
        return False
    reference = _utcnow() if now is None else now
    startup_window = max(CONTINUOUS_LEARNING_STALE_SECONDS, CONTINUOUS_LEARNING_HEARTBEAT_SECONDS * 2, 60)
    return state.last_started_at >= reference - timedelta(seconds=startup_window)


def _ownership_is_active(state: ContinuousLearningState | None, now: datetime | None = None) -> bool:
    if state is None or str(state.runtime_status or "").lower() not in {"starting", "running", "paused"}:
        return False
    if not is_process_running(state.active_pid):
        return False
    return _heartbeat_is_fresh(state, now) or _startup_is_fresh(state, now)


# ============================================================================
# SECTION: MODEL LIFECYCLE & PROMOTION
# ============================================================================
# Query active model versions and handle promotion workflows.

def _active_model_version() -> str | None:
    versions: list[str] = []
    for model_type in ("ml", "dl"):
        runs = list_model_runs(model_type)
        active = next((row for row in runs if row.get("is_active")), None)
        if active:
            versions.append(f"{model_type}:{active.get('run_id')}")
        elif runs:
            versions.append(f"{model_type}:{runs[0].get('run_id')}")
    return " | ".join(versions) if versions else None


def _review_and_promote(run_id: str | None) -> dict:
    if not run_id:
        return {"promoted_run_id": None, "review": None, "activation": None, "error": "Missing run_id."}
    review = review_model_promotion(run_id)
    if review.get("error"):
        return {"promoted_run_id": None, "review": review, "activation": None, "error": review.get("error")}
    if not review.get("approved"):
        return {"promoted_run_id": None, "review": review, "activation": None, "error": None}
    promotion = promote_model_run(run_id)
    return {
        "promoted_run_id": run_id if promotion.get("activation") else None,
        "review": review,
        "activation": promotion.get("activation"),
        "error": promotion.get("error"),
    }


# ============================================================================
# SECTION: PROCESS MANAGEMENT
# ============================================================================
# Spawn and lifecycle management of isolated continuous learning worker processes.

def _spawn_continuous_learning_process() -> tuple[bool, int | None, str | None]:
    command = [CONTINUOUS_LEARNING_RUNNER_PYTHON, "-m", "backend.app.workers.continuous_learning_runner"]
    log_path = _continuous_log_path()
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(f"[launcher] spawned_at={_utcnow().isoformat()} role={SERVER_ROLE}\n")

    stdout_handle = log_path.open("a", encoding="utf-8")
    popen_kwargs = {
        "cwd": str(ROOT_DIR),
        "stdout": stdout_handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "env": os.environ.copy(),
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        popen_kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **popen_kwargs)
        return True, process.pid, str(log_path)
    except Exception as exc:
        return False, None, " ".join(str(exc).split()) or exc.__class__.__name__
    finally:
        try:
            stdout_handle.close()
        except Exception:
            pass


def start_continuous_learning(requested_by: str | None = "api", force_spawn: bool = False) -> dict:
    if not ENABLE_CONTINUOUS_LEARNING:
        return {
            "enabled": False,
            "accepted": False,
            "runner_role_allowed": CONTINUOUS_LEARNING_ROLE_ALLOWED,
            "reason": "Continuous learning is disabled by configuration.",
        }

    with session_scope() as session:
        state = _get_or_create_state(session)
        state.desired_state = "running"
        state.updated_at = _utcnow()
        state_payload = _serialize_state(state)

    if not CONTINUOUS_LEARNING_ROLE_ALLOWED:
        return {
            "enabled": True,
            "accepted": False,
            "runner_role_allowed": False,
            "reason": f"Current server role '{SERVER_ROLE}' is not allowed to own the continuous learning worker. Runner role: '{CONTINUOUS_LEARNING_RUNNER_ROLE}'.",
            "state": state_payload,
        }

    with session_scope() as session:
        state = _get_or_create_state(session)
        ownership_active = _ownership_is_active(state)
        running = ownership_active
        if state.active_pid and not ownership_active and not is_process_running(state.active_pid):
            state.runtime_status = "idle"
            state.active_stage = "recovering"
            state.worker_id = None
            state.active_pid = None
            session.flush()
        state_payload = _serialize_state(state)

    if running and not force_spawn:
        return {
            "enabled": True,
            "accepted": True,
            "already_running": True,
            "runner_role_allowed": CONTINUOUS_LEARNING_ROLE_ALLOWED,
            "state": state_payload,
        }

    with session_scope() as session:
        state = _get_or_create_state(session)
        state.runtime_status = "starting"
        state.active_stage = "spawn_pending"
        state.last_started_at = _utcnow()
        state.next_cycle_at = _utcnow()
        session.flush()

    ok, pid, detail = _spawn_continuous_learning_process()
    with session_scope() as session:
        state = _get_or_create_state(session)
        if ok:
            state.active_pid = pid
            state.last_failure_reason = None
        else:
            state.runtime_status = "error"
            state.active_stage = "spawn_failed"
            state.last_failure_reason = detail
        session.flush()
        state_payload = _serialize_state(state)

    log_event(
        logger,
        logging.INFO if ok else logging.ERROR,
        "continuous_learning.start",
        requested_by=requested_by,
        accepted=ok,
        pid=pid,
        detail=detail,
    )
    return {
        "enabled": True,
        "accepted": ok,
        "runner_role_allowed": True,
        "pid": pid,
        "detail": detail,
        "state": state_payload,
    }


def pause_continuous_learning(requested_by: str | None = "api") -> dict:
    with session_scope() as session:
        state = _get_or_create_state(session)
        state.desired_state = "paused"
        if state.runtime_status == "idle":
            state.active_stage = "paused"
        state.updated_at = _utcnow()
        session.flush()
        payload = _serialize_state(state)
    log_event(logger, logging.INFO, "continuous_learning.pause", requested_by=requested_by)
    return {"enabled": ENABLE_CONTINUOUS_LEARNING, "accepted": True, "state": payload}


def resume_continuous_learning(requested_by: str | None = "api") -> dict:
    return start_continuous_learning(requested_by=requested_by, force_spawn=False)


def _create_run(session, cycle_type: str = "full") -> ContinuousLearningRun:
    now = _utcnow()
    row = ContinuousLearningRun(
        run_id=f"cl-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}",
        status="running",
        stage="bootstrapping",
        cycle_type=cycle_type,
        started_at=now,
    )
    session.add(row)
    session.flush()
    return row


# ============================================================================
# SECTION: WORKER MANAGEMENT
# ============================================================================
# Track worker process ownership, heartbeats, and exclusive access control.

def _update_stage(worker_id: str, run_id: str, stage: str, next_cycle_at: datetime | None = None) -> None:
    with session_scope() as session:
        state = _get_or_create_state(session)
        now = _utcnow()
        if state.worker_id not in {None, worker_id} and _ownership_is_active(state, now):
            raise RuntimeError("Continuous learning ownership changed during execution.")
        state.worker_id = worker_id
        state.active_pid = os.getpid()
        state.runtime_status = "running"
        state.active_stage = stage
        state.current_run_id = run_id
        state.last_heartbeat_at = now
        if next_cycle_at is not None:
            state.next_cycle_at = next_cycle_at
        run = session.query(ContinuousLearningRun).filter(ContinuousLearningRun.run_id == run_id).first()
        if run is not None:
            run.stage = stage
        session.flush()


def _touch_worker_heartbeat(worker_id: str, run_id: str, stage: str | None = None) -> None:
    with session_scope() as session:
        state = _get_or_create_state(session)
        now = _utcnow()
        if state.worker_id not in {None, worker_id} and _ownership_is_active(state, now):
            raise RuntimeError("Continuous learning ownership changed during execution.")
        state.worker_id = worker_id
        state.active_pid = os.getpid()
        state.runtime_status = "running"
        if stage:
            state.active_stage = stage
        state.current_run_id = run_id
        state.last_heartbeat_at = now
        session.flush()


def _claim_worker(worker_id: str, pid: int) -> tuple[bool, dict]:
    now = _utcnow()
    with session_scope() as session:
        state = _get_or_create_state(session)
        if (
            _ownership_is_active(state, now)
            and state.worker_id
            and state.worker_id != worker_id
        ):
            return False, _serialize_state(state)
        state.worker_id = worker_id
        state.active_pid = pid
        state.runtime_status = "starting"
        state.active_stage = "bootstrapping"
        state.last_started_at = now
        state.last_heartbeat_at = now
        state.next_cycle_at = now
        state.last_failure_reason = None
        session.flush()
        return True, _serialize_state(state)


def _release_worker(worker_id: str, status: str = "stopped", failure_reason: str | None = None) -> None:
    with session_scope() as session:
        state = _get_or_create_state(session)
        if state.worker_id == worker_id or not _ownership_is_active(state):
            state.runtime_status = status
            state.active_stage = "paused" if state.desired_state == "paused" else "idle"
            state.current_run_id = None
            state.worker_id = None if status in {"stopped", "idle", "error"} else state.worker_id
            state.active_pid = None if status in {"stopped", "idle", "error"} else state.active_pid
            state.last_heartbeat_at = _utcnow()
            state.last_failure_reason = failure_reason
            session.flush()


# ============================================================================
# SECTION: STATUS & MONITORING
# ============================================================================
# Build runtime state snapshots and health reports for dashboards and queries.

def _continuous_learning_blocked_reason() -> str | None:
    if not ENABLE_CONTINUOUS_LEARNING:
        return "Continuous learning is disabled by configuration."
    if not CONTINUOUS_LEARNING_ROLE_ALLOWED:
        return (
            f"Current server role '{SERVER_ROLE}' is not allowed to own the continuous learning worker. "
            f"Runner role: '{CONTINUOUS_LEARNING_RUNNER_ROLE}'."
        )
    return None


def _continuous_learning_runtime_state(state: ContinuousLearningState) -> str:
    blocked_reason = _continuous_learning_blocked_reason()
    if blocked_reason:
        return "disabled" if not ENABLE_CONTINUOUS_LEARNING else "blocked"

    ownership_active = _ownership_is_active(state)
    desired_state = str(state.desired_state or "").lower()
    runtime_status = str(state.runtime_status or "idle").lower()
    if runtime_status in {"error", "failed"}:
        return "error"
    if desired_state == "paused":
        if ownership_active:
            return "paused"
        return "pause_requested" if runtime_status not in {"idle", "stopped"} else "idle"
    if ownership_active:
        if runtime_status == "starting":
            return "starting"
        return "running"
    if runtime_status in {"running", "starting", "paused"}:
        return "stale"
    if runtime_status == "stopped":
        return "idle"
    return runtime_status or "idle"


def _build_continuous_learning_runtime_payload(state: ContinuousLearningState) -> dict:
    heartbeat_fresh = _heartbeat_is_fresh(state)
    startup_fresh = _startup_is_fresh(state)
    ownership_active = _ownership_is_active(state)
    runtime_state = _continuous_learning_runtime_state(state)
    blocked_reason = _continuous_learning_blocked_reason()
    payload = _serialize_state(state)
    payload["heartbeat_fresh"] = heartbeat_fresh
    payload["startup_fresh"] = startup_fresh
    payload["ownership_active"] = ownership_active
    payload["runtime_state"] = runtime_state
    return {
        "enabled": ENABLE_CONTINUOUS_LEARNING,
        "startup_enabled": CONTINUOUS_LEARNING_STARTUP_ENABLED,
        "runner_role": CONTINUOUS_LEARNING_RUNNER_ROLE,
        "runner_role_allowed": CONTINUOUS_LEARNING_ROLE_ALLOWED,
        "server_role": SERVER_ROLE,
        "cycle_seconds": CONTINUOUS_LEARNING_CYCLE_SECONDS,
        "heartbeat_seconds": CONTINUOUS_LEARNING_HEARTBEAT_SECONDS,
        "stale_seconds": CONTINUOUS_LEARNING_STALE_SECONDS,
        "runtime_state": runtime_state,
        "running": runtime_state in {"starting", "running"},
        "paused": runtime_state in {"paused", "pause_requested"},
        "blocked": blocked_reason is not None,
        "blocked_reason": blocked_reason,
        "owner": {
            "worker_id": state.worker_id,
            "pid": state.active_pid,
            "ownership_active": ownership_active,
            "heartbeat_fresh": heartbeat_fresh,
            "startup_fresh": startup_fresh,
        },
        "state": payload,
    }


def _record_artifact(session, *, run_id: str, artifact_type: str, artifact_key: str | None, payload: dict | list, file_name: str | None = None) -> ContinuousLearningArtifact:
    file_path = None
    if file_name:
        file_path = _write_json(_candidate_artifact_dir(run_id) / file_name, payload)
    row = ContinuousLearningArtifact(
        run_id=run_id,
        artifact_type=artifact_type,
        artifact_key=artifact_key,
        payload_json=dumps_json(payload),
        file_path=file_path,
    )
    session.add(row)
    session.flush()
    return row


def _run_with_heartbeat(worker_id: str, run_id: str, stage: str, func, *args, **kwargs):
    interval_seconds = max(5, min(CONTINUOUS_LEARNING_HEARTBEAT_SECONDS, 15))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        while True:
            try:
                return future.result(timeout=interval_seconds)
            except FutureTimeout:
                _touch_worker_heartbeat(worker_id, run_id, stage=stage)


# ============================================================================
# SECTION: MARKET & HISTORICAL DATA
# ============================================================================
# Load and refresh market data, resolve analysis/training symbol universes.

def _load_recent_policy_state() -> dict:
    with session_scope() as session:
        row = (
            session.query(ContinuousLearningArtifact)
            .filter(ContinuousLearningArtifact.artifact_type == "policy_state")
            .order_by(ContinuousLearningArtifact.created_at.desc())
            .first()
        )
        if row is None:
            return {}
        return loads_json(row.payload_json, default={})


def _get_learning_windows() -> tuple[str, str, str]:
    today = _utcnow().date()
    training_lookback = max(int(AUTONOMOUS_HISTORY_LOOKBACK_DAYS or 0) * 12, 365)
    evaluation_lookback = max(int(AUTONOMOUS_HISTORY_LOOKBACK_DAYS or 0) * 8, 180)
    analysis_start = str(today - timedelta(days=max(int(AUTONOMOUS_HISTORY_LOOKBACK_DAYS or 45), 45)))
    evaluation_start = str(today - timedelta(days=evaluation_lookback))
    training_start = str(today - timedelta(days=training_lookback))
    return training_start, evaluation_start, analysis_start


def _resolve_learning_symbols() -> dict:
    if AUTONOMOUS_REFRESH_UNIVERSE:
        try:
            refresh_market_universe(force=False)
        except Exception as exc:
            log_event(logger, logging.WARNING, "continuous_learning.universe_refresh.failed", error=str(exc))

    universe = resolve_universe_preset(AUTOMATION_DEFAULT_PRESET, limit=300)
    symbols = [str(symbol).strip().upper() for symbol in universe.get("symbols", []) if str(symbol).strip()]
    seeded = [str(symbol).strip().upper() for symbol in DEFAULT_SAMPLE_SYMBOLS if str(symbol).strip()]

    def _pick(limit: int) -> list[str]:
        picked: list[str] = []
        for symbol in seeded + symbols:
            if symbol in picked:
                continue
            picked.append(symbol)
            if len(picked) >= max(int(limit or 0), 1):
                break
        return picked or seeded or symbols[: max(int(limit or 0), 1)] or list(DEFAULT_SAMPLE_SYMBOLS)

    analysis_symbols = _pick(AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT)
    training_symbols = _pick(AUTONOMOUS_TRAIN_SYMBOL_LIMIT)
    evaluation_symbols = _pick(CONTINUOUS_LEARNING_EVALUATION_SYMBOLS)
    return {
        "preset": universe.get("preset"),
        "matched_count": universe.get("matched_count"),
        "analysis_symbols": analysis_symbols,
        "training_symbols": training_symbols,
        "evaluation_symbols": evaluation_symbols,
    }


def _refresh_learning_history(symbols: list[str]) -> dict:
    training_start, _, _ = _get_learning_windows()
    end_date = str(_utcnow().date())
    refreshed = []
    errors = []
    for symbol in symbols:
        try:
            result = load_history(symbol, training_start, end_date, interval="1d", persist=True)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": " ".join(str(exc).split()) or exc.__class__.__name__})
            continue
        if result.get("error"):
            errors.append({"symbol": symbol, "error": result.get("error")})
            continue
        refreshed.append({"symbol": symbol, "rows": _safe_int(result.get("rows")), "source": result.get("source")})
    return {
        "requested_symbols": len(symbols),
        "refreshed_symbols": len(refreshed),
        "errors": errors[:20],
        "sample": refreshed[:10],
        "window": {"start_date": training_start, "end_date": end_date},
    }


# ============================================================================
# SECTION: LEARNING CORE
# ============================================================================
# Outcome analysis, policy weight computation, and candidate strategy generation.

def _collect_outcome_snapshot() -> dict:
    since = _utcnow() - timedelta(days=max(CONTINUOUS_LEARNING_POLICY_LOOKBACK_DAYS, 14))
    with session_scope() as session:
        trades = (
            session.query(PaperTrade)
            .filter(PaperTrade.created_at >= since)
            .order_by(PaperTrade.created_at.desc())
            .limit(500)
            .all()
        )
        signals = (
            session.query(SignalHistory)
            .filter(SignalHistory.created_at >= since)
            .order_by(SignalHistory.created_at.desc())
            .limit(500)
            .all()
        )
        positions = session.query(PaperPosition).order_by(PaperPosition.updated_at.desc()).limit(100).all()
        evaluations = session.query(StrategyEvaluationRun).order_by(StrategyEvaluationRun.started_at.desc()).limit(50).all()
        analyses = session.query(AnalysisRun).order_by(AnalysisRun.run_at.desc()).limit(100).all()

    realized = [_safe_float(row.realized_pnl, default=0.0) for row in trades if row.realized_pnl is not None]
    confidence_values = [_safe_float(row.confidence, default=0.0) for row in signals if row.confidence is not None]
    open_exposure = sum(abs(_safe_float(row.market_value, default=0.0)) for row in positions if str(row.status or "").upper() == "OPEN")
    best_strategy_counts: dict[str, int] = {}
    for row in evaluations:
        metrics = loads_json(row.metrics_json, default={})
        best_strategy = str(metrics.get("best_strategy") or "").strip().lower()
        if best_strategy:
            best_strategy_counts[best_strategy] = best_strategy_counts.get(best_strategy, 0) + 1

    latest_analysis_signals: dict[str, int] = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for row in analyses[:40]:
        signal = str(row.signal or "HOLD").upper()
        latest_analysis_signals[signal] = latest_analysis_signals.get(signal, 0) + 1

    return {
        "captured_at": _utcnow().isoformat(),
        "paper_trade_count": len(trades),
        "signal_history_count": len(signals),
        "open_positions": sum(1 for row in positions if str(row.status or "").upper() == "OPEN"),
        "open_exposure": round(open_exposure, 4),
        "avg_realized_pnl": round(sum(realized) / len(realized), 4) if realized else 0.0,
        "winning_trade_ratio": round(sum(1 for value in realized if value > 0) / len(realized), 4) if realized else 0.0,
        "avg_signal_confidence": round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0.0,
        "best_strategy_counts": best_strategy_counts,
        "recent_analysis_signals": latest_analysis_signals,
    }


def _build_policy_weights(outcomes: dict, previous_state: dict) -> dict:
    weights = {
        "factor": 1.0,
        "momentum": 1.0,
        "mean_reversion": 1.0,
        "volatility": 1.0,
        "hybrid_ml": 1.0,
        "ensemble": 1.0,
    }
    previous_weights = (previous_state or {}).get("weights") or {}
    for family, default_value in weights.items():
        base = _safe_float(previous_weights.get(family), default_value)
        weights[family] = min(max(base, 0.75), 1.35)

    avg_realized_pnl = _safe_float(outcomes.get("avg_realized_pnl"))
    winning_ratio = _safe_float(outcomes.get("winning_trade_ratio"))
    avg_confidence = _safe_float(outcomes.get("avg_signal_confidence"))
    best_strategy_counts = outcomes.get("best_strategy_counts") or {}

    if avg_realized_pnl > 0:
        weights["hybrid_ml"] += 0.08
        weights["ensemble"] += 0.06
    elif avg_realized_pnl < 0:
        weights["mean_reversion"] += 0.04
        weights["volatility"] += 0.03

    if winning_ratio >= 0.55:
        weights["momentum"] += 0.05
        weights["factor"] += 0.04
    elif winning_ratio and winning_ratio < 0.45:
        weights["mean_reversion"] += 0.05

    if avg_confidence >= 60:
        weights["ensemble"] += 0.05
        weights["hybrid_ml"] += 0.05

    if best_strategy_counts.get("ensemble"):
        weights["ensemble"] += min(best_strategy_counts["ensemble"] * 0.01, 0.08)
    if best_strategy_counts.get("ml") or best_strategy_counts.get("dl"):
        weights["hybrid_ml"] += min((best_strategy_counts.get("ml", 0) + best_strategy_counts.get("dl", 0)) * 0.01, 0.08)
    if best_strategy_counts.get("classic"):
        weights["factor"] += min(best_strategy_counts["classic"] * 0.01, 0.06)
    if best_strategy_counts.get("vectorbt"):
        weights["momentum"] += min(best_strategy_counts["vectorbt"] * 0.01, 0.05)

    normalized = {key: round(min(max(value, 0.75), 1.35), 4) for key, value in weights.items()}
    return {
        "captured_at": _utcnow().isoformat(),
        "weights": normalized,
        "inputs": {
            "avg_realized_pnl": avg_realized_pnl,
            "winning_trade_ratio": winning_ratio,
            "avg_signal_confidence": avg_confidence,
            "best_strategy_counts": best_strategy_counts,
        },
    }


def _build_live_rankings(symbols: list[str], analysis_start: str, end_date: str) -> list[dict]:
    def _analyze(symbol: str) -> dict:
        try:
            return build_smart_analysis(symbol, analysis_start, end_date, include_dl=AUTONOMOUS_INCLUDE_DL, include_ensemble=True)
        except Exception as exc:
            return {"instrument": symbol, "error": " ".join(str(exc).split()) or exc.__class__.__name__}

    max_workers = max(1, min(len(symbols), 4))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        items = list(executor.map(_analyze, symbols))
    clean = [row for row in items if not row.get("error")]
    clean.sort(key=lambda row: (_safe_float(row.get("rank_score"), -9999), _safe_float(row.get("confidence"), 0.0)), reverse=True)
    return clean


def _candidate_live_bias(candidate: dict, live_rankings: list[dict]) -> float:
    if not live_rankings:
        return 0.0
    family = candidate.get("family")
    sample = live_rankings[: min(len(live_rankings), 5)]
    score = 0.0
    for row in sample:
        smart_signal = str(row.get("smart_signal") or row.get("enhanced_signal") or row.get("signal") or "HOLD").upper()
        mtf_score = _safe_float(row.get("mtf_score"))
        rs_score = _safe_float(row.get("rs_score"))
        squeeze_ready = bool(row.get("squeeze_ready"))
        smart_confidence = _safe_float(row.get("smart_confidence", row.get("confidence")))
        if family == "momentum":
            if smart_signal == "BUY" and mtf_score > 0 and rs_score > 0:
                score += 2.0
        elif family == "mean_reversion":
            if abs(_safe_float(row.get("technical_score"))) >= 2 and smart_signal in {"BUY", "SELL"}:
                score += 1.25
        elif family == "volatility":
            if squeeze_ready:
                score += 1.8
        elif family == "hybrid_ml":
            score += smart_confidence / 100.0
        elif family == "ensemble":
            if smart_signal != "HOLD":
                score += 1.6
        else:
            if smart_signal in {"BUY", "SELL"}:
                score += 1.2
    return round(score / max(len(sample), 1), 4)


def _aggregate_candidate_events(events: list[dict]) -> dict:
    if not events:
        return {
            "trade_count": 0,
            "win_rate_pct": 0.0,
            "avg_trade_return_pct": 0.0,
            "expectancy_pct": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }

    returns = [_safe_float(item.get("trade_return_pct")) for item in events]
    wins = sum(1 for value in returns if value > 0)
    losses = [value for value in returns if value <= 0]
    win_rate_pct = (wins / len(returns)) * 100.0
    avg_trade_return_pct = sum(returns) / len(returns)
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    expectancy_pct = avg_trade_return_pct if avg_loss == 0 else avg_trade_return_pct / max(avg_loss, 0.0001)

    equity = 100.0
    peak = 100.0
    max_drawdown_pct = 0.0
    for trade_return in returns:
        equity *= 1.0 + (trade_return / 100.0)
        peak = max(peak, equity)
        drawdown_pct = 0.0 if peak <= 0 else ((peak - equity) / peak) * 100.0
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
    total_return_pct = ((equity / 100.0) - 1.0) * 100.0

    return {
        "trade_count": len(events),
        "win_rate_pct": round(win_rate_pct, 4),
        "avg_trade_return_pct": round(avg_trade_return_pct, 4),
        "expectancy_pct": round(expectancy_pct, 4),
        "total_return_pct": round(total_return_pct, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
    }


# ============================================================================
# SECTION: CANDIDATE EVALUATION
# ============================================================================
# Backtest candidate strategies and compute performance metrics.

def _evaluate_candidate(candidate: dict, symbols: list[str], evaluation_start: str, end_date: str, live_rankings: list[dict], policy_weights: dict) -> dict:
    evaluated_symbols = []
    all_events: list[dict] = []
    params = dict(candidate.get("params") or {})
    for symbol in symbols:
        result = backtest_symbol_enhanced(
            instrument=symbol,
            start_date=evaluation_start,
            end_date=end_date,
            hold_days=params.get("hold_days", 10),
            min_technical_score=params.get("min_technical_score", 2),
            buy_score_threshold=params.get("buy_score_threshold", 3),
            sell_score_threshold=params.get("sell_score_threshold", 4),
        )
        if result.get("error"):
            evaluated_symbols.append({"symbol": symbol, "status": "error", "error": result.get("error")})
            continue
        events = result.get("events") or []
        evaluated_symbols.append({
            "symbol": symbol,
            "status": "ok",
            "trades": _safe_int(result.get("trades")),
            "win_rate_pct": _safe_float(result.get("overall_win_rate_pct")),
            "avg_trade_return_pct": _safe_float(result.get("avg_trade_return_pct")),
        })
        for event in events:
            all_events.append({**event, "symbol": symbol})

    metrics = _aggregate_candidate_events(all_events)
    live_bias = _candidate_live_bias(candidate, live_rankings)
    policy_weight = _safe_float(policy_weights.get(candidate.get("family")), 1.0)
    robust_score = _score_formula(
        total_return_pct=_safe_float(metrics.get("total_return_pct")),
        win_rate_pct=_safe_float(metrics.get("win_rate_pct")),
        max_drawdown_pct=_safe_float(metrics.get("max_drawdown_pct")),
        expectancy_pct=_safe_float(metrics.get("expectancy_pct")),
    )
    final_score = round((robust_score * policy_weight) + (live_bias * 10.0), 4)
    anchor_symbol = next((row.get("instrument") for row in live_rankings if row.get("instrument")), None)
    return {
        "candidate_name": candidate.get("name"),
        "family": candidate.get("family"),
        "description": candidate.get("description"),
        "params": params,
        "policy_weight": round(policy_weight, 4),
        "live_bias": live_bias,
        "anchor_symbol": anchor_symbol,
        "score": final_score,
        "robust_score": robust_score,
        "metrics": metrics,
        "evaluated_symbols": evaluated_symbols,
    }


def _generate_candidates(policy_state: dict, live_rankings: list[dict]) -> list[dict]:
    weights = (policy_state or {}).get("weights") or {}
    generated = []
    for blueprint in CANDIDATE_BLUEPRINTS[: max(CONTINUOUS_LEARNING_MAX_CANDIDATES, 1)]:
        generated.append({
            **blueprint,
            "policy_weight": _safe_float(weights.get(blueprint["family"]), 1.0),
            "top_live_symbol": live_rankings[0].get("instrument") if live_rankings else None,
        })
    return generated


def _evaluate_candidates_batch(
    generated_candidates: list[dict],
    evaluation_symbols: list[str],
    evaluation_start: str,
    end_date: str,
    live_rankings: list[dict],
    policy_weights: dict,
) -> list[dict]:
    return [
        _evaluate_candidate(candidate, evaluation_symbols, evaluation_start, end_date, live_rankings, policy_weights)
        for candidate in generated_candidates
    ]


def _record_strategy_lab_candidates(session, run_id: str, ranked_candidates: list[dict], summary: dict) -> str | None:
    if not ranked_candidates:
        return None
    strategy_run_id = f"clab-{run_id}"
    best_candidate = ranked_candidates[0]
    exists = (
        session.query(StrategyEvaluationRun)
        .filter(StrategyEvaluationRun.run_id == strategy_run_id)
        .first()
    )
    if exists is not None:
        return strategy_run_id
    session.add(StrategyEvaluationRun(
        run_id=strategy_run_id,
        instrument=str(best_candidate.get("anchor_symbol") or best_candidate.get("candidate_name") or "AUTO")[:20],
        status="completed",
        completed_at=_utcnow(),
        config_json=dumps_json({
            "source": "continuous_learning",
            "candidate_name": best_candidate.get("candidate_name"),
            "family": best_candidate.get("family"),
            "params": best_candidate.get("params"),
        }),
        metrics_json=dumps_json(summary),
        leaderboard_json=dumps_json(ranked_candidates),
        notes="Continuous learning generated candidate set.",
    ))
    return strategy_run_id


# ============================================================================
# SECTION: CYCLE EXECUTION
# ============================================================================
# Main orchestration of a complete learning cycle: refresh -> analyze -> train -> evaluate -> promote.

def _run_cycle(worker_id: str) -> dict:
    with session_scope() as session:
        run = _create_run(session, cycle_type="full")
        run_id = run.run_id
        state = _get_or_create_state(session)
        state.runtime_status = "running"
        state.active_stage = "market_refresh"
        state.current_run_id = run_id
        state.worker_id = worker_id
        state.last_cycle_started_at = _utcnow()
        state.last_heartbeat_at = _utcnow()
        state.next_cycle_at = _utcnow() + timedelta(seconds=max(CONTINUOUS_LEARNING_CYCLE_SECONDS, 60))
        session.flush()

    training_start, evaluation_start, analysis_start = _get_learning_windows()
    end_date = str(_utcnow().date())
    universe_info = _resolve_learning_symbols()

    cycle = {
        "run_id": run_id,
        "started_at": _utcnow().isoformat(),
        "windows": {
            "training_start": training_start,
            "evaluation_start": evaluation_start,
            "analysis_start": analysis_start,
            "end_date": end_date,
        },
        "universe": universe_info,
        "training": {},
        "promotion": {},
        "artifacts": {},
    }

    _update_stage(worker_id, run_id, "market_refresh")
    history_refresh = _refresh_learning_history(universe_info["training_symbols"])
    snapshots = fetch_quote_snapshots(universe_info["analysis_symbols"], include_profile=False)
    cycle["market_refresh"] = {
        "history_refresh": history_refresh,
        "snapshots": {
            "count": snapshots.get("count", 0),
            "failed_symbols": snapshots.get("failed_symbols", 0),
            "provider_status": snapshots.get("provider_status"),
            "errors": snapshots.get("errors", [])[:10],
        },
    }

    _update_stage(worker_id, run_id, "outcome_ingestion")
    outcomes = _collect_outcome_snapshot()
    previous_policy = _load_recent_policy_state()
    policy_state = _build_policy_weights(outcomes, previous_policy)
    cycle["outcomes"] = outcomes
    cycle["policy_state"] = policy_state

    _update_stage(worker_id, run_id, "model_training")
    ml_training = {"status": "skipped", "reason": "Auto retraining is disabled."}
    dl_training = {"status": "skipped", "reason": "DL training is disabled for this loop."}
    ml_promotion = {"promoted_run_id": None, "error": None}
    dl_promotion = {"promoted_run_id": None, "error": None}
    if ENABLE_AUTO_RETRAIN:
        ml_training = _run_with_heartbeat(
            worker_id,
            run_id,
            "model_training",
            train_ml_models,
            symbols=universe_info["training_symbols"],
            start_date=training_start,
            end_date=end_date,
            set_active=False,
        )
        ml_promotion = _review_and_promote(ml_training.get("run_id"))
        if AUTONOMOUS_INCLUDE_DL:
            dl_training = _run_with_heartbeat(
                worker_id,
                run_id,
                "model_training",
                train_dl_models,
                symbols=universe_info["training_symbols"],
                start_date=training_start,
                end_date=end_date,
                set_active=False,
            )
            dl_promotion = _review_and_promote(dl_training.get("run_id"))
    cycle["training"] = {"ml": ml_training, "dl": dl_training}
    cycle["promotion"] = {"ml": ml_promotion, "dl": dl_promotion}

    _update_stage(worker_id, run_id, "live_analysis")
    live_rankings = _run_with_heartbeat(
        worker_id,
        run_id,
        "live_analysis",
        _build_live_rankings,
        universe_info["analysis_symbols"],
        analysis_start,
        end_date,
    )
    cycle["live_rankings"] = [
        {
            "instrument": row.get("instrument"),
            "signal": row.get("smart_signal") or row.get("enhanced_signal") or row.get("signal"),
            "confidence": row.get("smart_confidence", row.get("confidence")),
            "setup_type": row.get("setup_type"),
            "rank_score": row.get("rank_score"),
        }
        for row in live_rankings[:10]
    ]

    _update_stage(worker_id, run_id, "candidate_generation")
    generated_candidates = _generate_candidates(policy_state, live_rankings)
    cycle["generated_candidates"] = generated_candidates

    _update_stage(worker_id, run_id, "candidate_evaluation")
    evaluated = _run_with_heartbeat(
        worker_id,
        run_id,
        "candidate_evaluation",
        _evaluate_candidates_batch,
        generated_candidates,
        universe_info["evaluation_symbols"],
        evaluation_start,
        end_date,
        live_rankings,
        policy_state.get("weights") or {},
    )
    ranked_candidates = sorted(
        evaluated,
        key=lambda item: (_safe_float(item.get("score"), -9999), _safe_float((item.get("metrics") or {}).get("total_return_pct"), -9999)),
        reverse=True,
    )
    cycle["ranked_candidates"] = ranked_candidates
    best_candidate = ranked_candidates[0] if ranked_candidates else None

    _update_stage(worker_id, run_id, "artifact_persistence")
    summary = {
        "run_id": run_id,
        "completed_at": _utcnow().isoformat(),
        "model_version": _active_model_version(),
        "best_candidate": best_candidate,
        "evaluation_count": len(ranked_candidates),
        "market_refresh": cycle["market_refresh"],
        "outcomes": outcomes,
    }

    with session_scope() as session:
        policy_artifact = _record_artifact(session, run_id=run_id, artifact_type="policy_state", artifact_key="latest", payload=policy_state, file_name="policy_state.json")
        ranked_artifact = _record_artifact(session, run_id=run_id, artifact_type="strategy_candidates_ranked", artifact_key="latest", payload=ranked_candidates, file_name="ranked_candidates.json")
        summary_artifact = _record_artifact(session, run_id=run_id, artifact_type="cycle_summary", artifact_key="latest", payload=summary, file_name="summary.json")
        _record_artifact(session, run_id=run_id, artifact_type="outcome_snapshot", artifact_key="latest", payload=outcomes, file_name="outcomes.json")
        _record_artifact(session, run_id=run_id, artifact_type="training_result", artifact_key="ml", payload=ml_training, file_name="training_ml.json")
        _record_artifact(session, run_id=run_id, artifact_type="promotion_review", artifact_key="ml", payload=ml_promotion, file_name="promotion_ml.json")
        if AUTONOMOUS_INCLUDE_DL:
            _record_artifact(session, run_id=run_id, artifact_type="training_result", artifact_key="dl", payload=dl_training, file_name="training_dl.json")
            _record_artifact(session, run_id=run_id, artifact_type="promotion_review", artifact_key="dl", payload=dl_promotion, file_name="promotion_dl.json")

        strategy_lab_run_id = _record_strategy_lab_candidates(session, run_id, ranked_candidates[:5], summary)

        run = session.query(ContinuousLearningRun).filter(ContinuousLearningRun.run_id == run_id).first()
        state = _get_or_create_state(session)
        completed_at = _utcnow()
        if run is not None:
            run.status = "completed"
            run.stage = "completed"
            run.completed_at = completed_at
            run.duration_seconds = round((completed_at - run.started_at).total_seconds(), 4) if run.started_at else None
            run.summary_json = dumps_json(summary)
            run.metrics_json = dumps_json({
                "policy_state": policy_state,
                "best_candidate": best_candidate,
                "training": cycle["training"],
            })
            run.error_message = None
        state.runtime_status = "running"
        state.active_stage = "idle"
        state.current_run_id = run_id
        state.last_heartbeat_at = completed_at
        state.last_success_at = completed_at
        state.last_cycle_completed_at = completed_at
        state.next_cycle_at = completed_at + timedelta(seconds=max(CONTINUOUS_LEARNING_CYCLE_SECONDS, 60))
        state.current_model_version = _active_model_version()
        state.best_strategy_name = None if best_candidate is None else str(best_candidate.get("candidate_name"))
        state.best_strategy_run_id = strategy_lab_run_id
        state.latest_metrics_json = dumps_json({
            "policy_state": policy_state,
            "best_candidate": best_candidate,
            "latest_evaluation": ranked_candidates[:5],
            "strategy_lab_run_id": strategy_lab_run_id,
        })
        state.latest_artifact_path = summary_artifact.file_path or ranked_artifact.file_path or policy_artifact.file_path
        state.last_failure_reason = None
        session.flush()

    log_event(
        logger,
        logging.INFO,
        "continuous_learning.cycle.completed",
        run_id=run_id,
        best_candidate=None if best_candidate is None else best_candidate.get("candidate_name"),
        strategy_lab_run_id=strategy_lab_run_id,
    )
    return summary


def _mark_cycle_failed(worker_id: str, run_id: str | None, exc: Exception) -> None:
    error_message = " ".join(str(exc).split()) or exc.__class__.__name__
    with session_scope() as session:
        state = _get_or_create_state(session)
        target_run_id = run_id or state.current_run_id
        if target_run_id:
            run = session.query(ContinuousLearningRun).filter(ContinuousLearningRun.run_id == target_run_id).first()
            if run is not None:
                completed_at = _utcnow()
                run.status = "error"
                run.stage = "failed"
                run.completed_at = completed_at
                run.duration_seconds = round((completed_at - run.started_at).total_seconds(), 4) if run.started_at else None
                run.error_message = error_message
        if state.worker_id in {None, worker_id}:
            state.runtime_status = "error"
            state.active_stage = "failed"
            state.current_run_id = target_run_id
            state.last_heartbeat_at = _utcnow()
            state.last_failure_reason = error_message
            state.next_cycle_at = _utcnow() + timedelta(seconds=max(CONTINUOUS_LEARNING_CYCLE_SECONDS, 60))
        session.flush()
    log_event(logger, logging.ERROR, "continuous_learning.cycle.failed", run_id=target_run_id, error=error_message)


def run_continuous_learning_loop() -> int:
    ensure_runtime_directories()
    worker_id = f"worker-{os.getpid()}-{uuid4().hex[:8]}"
    claimed, state_payload = _claim_worker(worker_id, os.getpid())
    if not claimed:
        log_event(logger, logging.WARNING, "continuous_learning.worker.blocked", worker_id=worker_id, state=state_payload)
        return 0

    log_event(logger, logging.INFO, "continuous_learning.worker.started", worker_id=worker_id, pid=os.getpid())
    try:
        while True:
            with session_scope() as session:
                state = _get_or_create_state(session)
                desired_state = state.desired_state
                next_cycle_at = state.next_cycle_at
                last_heartbeat = state.last_heartbeat_at
            if desired_state == "paused":
                with session_scope() as session:
                    state = _get_or_create_state(session)
                    if state.worker_id not in {None, worker_id} and _ownership_is_active(state):
                        return 0
                    state.worker_id = worker_id
                    state.active_pid = os.getpid()
                    state.runtime_status = "paused"
                    state.active_stage = "paused"
                    state.last_heartbeat_at = _utcnow()
                    state.next_cycle_at = _utcnow() + timedelta(seconds=max(CONTINUOUS_LEARNING_PAUSE_SECONDS, 10))
                    session.flush()
                time.sleep(max(CONTINUOUS_LEARNING_PAUSE_SECONDS, 10))
                continue

            now = _utcnow()
            heartbeat_window = max(CONTINUOUS_LEARNING_HEARTBEAT_SECONDS, 15)
            if next_cycle_at and next_cycle_at > now and (last_heartbeat is None or last_heartbeat >= now - timedelta(seconds=heartbeat_window)):
                with session_scope() as session:
                    state = _get_or_create_state(session)
                    if state.worker_id not in {None, worker_id} and _ownership_is_active(state):
                        return 0
                    state.worker_id = worker_id
                    state.active_pid = os.getpid()
                    state.runtime_status = "running"
                    state.active_stage = "sleeping"
                    state.last_heartbeat_at = now
                    session.flush()
                sleep_seconds = min(max((next_cycle_at - now).total_seconds(), 1), heartbeat_window)
                time.sleep(sleep_seconds)
                continue

            current_run_id = None
            try:
                summary = _run_cycle(worker_id)
                current_run_id = summary.get("run_id")
            except Exception as exc:
                _mark_cycle_failed(worker_id, current_run_id, exc)
                time.sleep(max(min(CONTINUOUS_LEARNING_CYCLE_SECONDS, 60), 15))
                continue
    finally:
        _release_worker(worker_id, status="stopped")
        log_event(logger, logging.INFO, "continuous_learning.worker.stopped", worker_id=worker_id)


# ============================================================================
# SECTION: PUBLIC API
# ============================================================================
# User-facing functions for querying status, managing lifecycle, and retrieving artifacts.

def get_continuous_learning_status(limit: int = 10) -> dict:
    limit = max(1, min(int(limit or 10), 50))
    with session_scope() as session:
        state = _get_or_create_state(session)
        runs = session.query(ContinuousLearningRun).order_by(ContinuousLearningRun.started_at.desc()).limit(limit).all()
        artifacts = session.query(ContinuousLearningArtifact).order_by(ContinuousLearningArtifact.created_at.desc()).limit(limit).all()
    runtime = _build_continuous_learning_runtime_payload(state)
    return {
        "engine": {
            "enabled": ENABLE_CONTINUOUS_LEARNING,
            "runner_role": CONTINUOUS_LEARNING_RUNNER_ROLE,
            "runner_role_allowed": CONTINUOUS_LEARNING_ROLE_ALLOWED,
            "server_role": SERVER_ROLE,
            "cycle_seconds": CONTINUOUS_LEARNING_CYCLE_SECONDS,
            "heartbeat_seconds": CONTINUOUS_LEARNING_HEARTBEAT_SECONDS,
            "stale_seconds": CONTINUOUS_LEARNING_STALE_SECONDS,
            "startup_enabled": CONTINUOUS_LEARNING_STARTUP_ENABLED,
        },
        "runtime": runtime,
        "state": runtime.get("state", _serialize_state(state)),
        "recent_runs": [_serialize_run(row) for row in runs],
        "recent_artifacts": [_serialize_artifact(row) for row in artifacts],
    }


def get_continuous_learning_runtime_snapshot() -> dict:
    with session_scope() as session:
        state = _get_or_create_state(session)
    return _build_continuous_learning_runtime_payload(state)


def list_continuous_learning_artifacts(limit: int = 20) -> dict:
    limit = max(1, min(int(limit or 20), 100))
    with session_scope() as session:
        rows = session.query(ContinuousLearningArtifact).order_by(ContinuousLearningArtifact.created_at.desc()).limit(limit).all()
    return {"items": [_serialize_artifact(row) for row in rows], "count": len(rows)}


def list_generated_strategy_candidates(limit: int = 10) -> dict:
    limit = max(1, min(int(limit or 10), 50))
    with session_scope() as session:
        rows = (
            session.query(ContinuousLearningArtifact)
            .filter(ContinuousLearningArtifact.artifact_type == "strategy_candidates_ranked")
            .order_by(ContinuousLearningArtifact.created_at.desc())
            .limit(limit)
            .all()
        )
    items = []
    for row in rows:
        payload = loads_json(row.payload_json, default=[])
        items.append({
            "run_id": row.run_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "candidates": payload[:5] if isinstance(payload, list) else [],
            "file_path": row.file_path,
        })
    latest = items[0] if items else {"candidates": []}
    return {
        "latest_run_id": latest.get("run_id"),
        "latest_created_at": latest.get("created_at"),
        "latest_candidates": latest.get("candidates", []),
        "items": items,
        "count": len(items),
    }
