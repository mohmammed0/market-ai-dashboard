from __future__ import annotations

import logging

from backend.app.config import (
    ALERT_CYCLE_MINUTES,
    AUTOMATION_DAILY_SUMMARY_HOUR,
    BREADTH_CYCLE_MINUTES,
    AUTONOMOUS_CYCLE_HOURS,
    AUTO_TRADING_CYCLE_MINUTES,
    CONTINUOUS_LEARNING_STARTUP_ENABLED,
    ENABLE_AUTO_RETRAIN,
    ENABLE_AUTONOMOUS_CYCLE,
    ENABLE_SCHEDULER,
    MARKET_CYCLE_MINUTES,
    NEWS_REFRESH_MINUTES,
    NEWS_REFRESH_PER_SYMBOL_LIMIT,
    RETRAIN_CYCLE_HOURS,
    SCHEDULER_ROLE_ALLOWED,
    SCHEDULER_RUNNER_ROLE,
    SERVER_ROLE,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models import SchedulerRun
from backend.app.application.model_lifecycle.training_jobs import reconcile_stale_training_jobs
from backend.app.services.background_jobs import reconcile_stale_jobs
from backend.app.services.continuous_learning import start_continuous_learning
from backend.app.services.automation_hub import run_automation_job
from backend.app.services.market_data import DEFAULT_SYMBOLS, fetch_quote_snapshots, incremental_update
from backend.app.services.news_feed import refresh_news_feed
from backend.app.services.storage import session_scope

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:  # pragma: no cover - optional dependency
    BackgroundScheduler = None


_scheduler = None
_jobs_registered = False
_last_continuous_learning_start_result = None
logger = get_logger(__name__)


def can_current_process_run_scheduler() -> bool:
    return bool(SCHEDULER_ROLE_ALLOWED)


def _scheduler_blocked_reason() -> str | None:
    if not ENABLE_SCHEDULER:
        return "Scheduler is disabled by configuration."
    if not can_current_process_run_scheduler():
        return (
            f"Current server role '{SERVER_ROLE}' is not allowed to run the scheduler. "
            f"Set MARKET_AI_SCHEDULER_RUNNER_ROLE={SERVER_ROLE} if this process should own it."
        )
    if BackgroundScheduler is None:
        return "APScheduler is not installed."
    return None


def _scheduler_runtime_state() -> str:
    blocked_reason = _scheduler_blocked_reason()
    if blocked_reason:
        return "disabled" if not ENABLE_SCHEDULER else "blocked"
    if _scheduler is not None and _scheduler.running:
        return "running"
    return "idle"


def _record_job(job_name, status, detail):
    log_event(logger, logging.INFO if status == "completed" else logging.WARNING, "scheduler.job.recorded", job_name=job_name, status=status, detail=detail)
    with session_scope() as session:
        session.add(SchedulerRun(job_name=job_name, status=status, detail=detail))


def _refresh_history_job():
    updated = 0
    errors = []
    try:
        for symbol in DEFAULT_SYMBOLS:
            try:
                result = incremental_update(symbol)
            except Exception as exc:
                errors.append(f"{symbol}: {' '.join(str(exc).split()) or exc.__class__.__name__}")
                continue
            if result.get("error"):
                errors.append(f"{symbol}: {result.get('error')}")
                continue
            updated += int(result.get("rows", 0))

        detail = f"updated_rows={updated} failed_symbols={len(errors)}"
        if errors:
            detail = f"{detail} sample_errors={errors[:3]}"
        _record_job("history_refresh", "completed", detail)
    except Exception as exc:
        _record_job("history_refresh", "error", str(exc))


def _refresh_quotes_job():
    try:
        result = fetch_quote_snapshots(DEFAULT_SYMBOLS)
        detail = f"snapshots={result.get('count', 0)} failed_symbols={result.get('failed_symbols', 0)}"
        if result.get("errors"):
            detail = f"{detail} sample_errors={result.get('errors', [])[:3]}"
        _record_job("quote_snapshot", "completed", detail)
    except Exception as exc:
        _record_job("quote_snapshot", "error", str(exc))


def _refresh_news_feed_job():
    try:
        result = refresh_news_feed(None, per_symbol_limit=NEWS_REFRESH_PER_SYMBOL_LIMIT)
        detail = (
            f"symbols={len(result.get('symbols', []) or [])} "
            f"fetched={result.get('fetched', 0)} "
            f"inserted={result.get('inserted', 0)} "
            f"skipped={result.get('skipped', 0)} "
            f"errors={len(result.get('errors', []) or [])}"
        )
        _record_job("news_refresh", "completed", detail)
    except Exception as exc:
        _record_job("news_refresh", "error", str(exc))


def _run_automation_job(job_name):
    try:
        preset = None
        if str(job_name or "").strip().lower() == "auto_trading_cycle":
            try:
                from backend.app.services.runtime_settings import get_auto_trading_config

                preset = str(get_auto_trading_config().get("universe_preset") or "").strip().upper() or None
            except Exception:
                preset = None
        result = run_automation_job(job_name=job_name, dry_run=False, preset=preset or AUTOMATION_DEFAULT_PRESET)
        _record_job(job_name, result.get("status", "completed"), result.get("detail", "ok"))
    except Exception as exc:
        _record_job(job_name, "error", str(exc))


def _maintenance_reconcile_job():
    """Reconcile stale background jobs and training jobs on a timer.

    This ensures crashed or killed worker processes are detected and their DB
    records transitioned to *failed* even when no client polls a status endpoint.
    Without this, a single crashed job can hold a concurrency slot indefinitely.
    """
    try:
        bg_changed = reconcile_stale_jobs()
        train_changed = reconcile_stale_training_jobs()
        detail = f"bg_jobs_reconciled={bg_changed} training_jobs_reconciled={train_changed}"
        _record_job("maintenance_reconcile", "completed", detail)
    except Exception as exc:
        _record_job("maintenance_reconcile", "error", str(exc))


def _run_trailing_stop_job():
    """Check all positions for trailing stop triggers."""
    try:
        from backend.app.services.trailing_stop_monitor import run_trailing_stop_check
        result = run_trailing_stop_check()
        detail = f"checked={result.get('checked', 0)} triggered={result.get('triggered', 0)} updated={result.get('updated', 0)}"
        _record_job("trailing_stop_check", "completed", detail)
    except Exception as exc:
        _record_job("trailing_stop_check", "error", str(exc))


def _run_smart_cycle_job():
    """Run AI-powered smart automation cycle."""
    try:
        import asyncio
        from backend.app.services.smart_automation import run_smart_cycle
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run_smart_cycle())
        finally:
            loop.close()
        detail = f"opportunities={result.get('opportunities_found', 0)} alerts={result.get('alerts_generated', 0)}"
        _record_job("smart_cycle", "completed", detail)
    except Exception as exc:
        _record_job("smart_cycle", "error", str(exc))


def _runtime_auto_trading_cycle_minutes() -> int:
    try:
        from backend.app.services.runtime_settings import get_auto_trading_config

        cycle_minutes = int(get_auto_trading_config().get("cycle_minutes") or AUTO_TRADING_CYCLE_MINUTES)
        return max(1, min(cycle_minutes, 720))
    except Exception:
        return max(1, int(AUTO_TRADING_CYCLE_MINUTES))


def sync_auto_trading_schedule() -> dict:
    if _scheduler is None:
        return {"updated": False, "reason": "scheduler_not_initialized"}

    minutes = _runtime_auto_trading_cycle_minutes()
    job = _scheduler.get_job("auto_trading_cycle")
    if job is None:
        _scheduler.add_job(
            lambda: _run_automation_job("auto_trading_cycle"),
            "interval",
            minutes=minutes,
            id="auto_trading_cycle",
            replace_existing=True,
        )
        return {"updated": True, "action": "added", "minutes": minutes}

    current_minutes = None
    interval = getattr(getattr(job, "trigger", None), "interval", None)
    if interval is not None:
        try:
            current_minutes = max(1, int(interval.total_seconds() // 60))
        except Exception:
            current_minutes = None
    if current_minutes == minutes:
        return {"updated": False, "action": "unchanged", "minutes": minutes}

    job.reschedule(trigger="interval", minutes=minutes)
    return {"updated": True, "action": "rescheduled", "minutes": minutes}


def _sync_auto_trading_schedule_job():
    try:
        result = sync_auto_trading_schedule()
        if result.get("updated"):
            log_event(
                logger,
                logging.INFO,
                "scheduler.auto_trading_schedule_synced",
                action=result.get("action"),
                minutes=result.get("minutes"),
            )
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "scheduler.auto_trading_schedule_sync_failed",
            error=str(exc),
        )


def start_scheduler():
    global _scheduler, _jobs_registered, _last_continuous_learning_start_result
    blocked_reason = _scheduler_blocked_reason()
    if blocked_reason is not None:
        log_event(
            logger,
            logging.INFO if not ENABLE_SCHEDULER else logging.WARNING,
            "scheduler.start.blocked",
            role=SERVER_ROLE,
            runner_role=SCHEDULER_RUNNER_ROLE,
            reason=blocked_reason,
        )
        return {
            "enabled": ENABLE_SCHEDULER,
            "running": False,
            "blocked": True,
            "reason": blocked_reason,
            "runtime_state": _scheduler_runtime_state(),
        }
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
    if not _jobs_registered:
        _scheduler.add_job(_refresh_history_job, "interval", minutes=30, id="history_refresh", replace_existing=True)
        _scheduler.add_job(_refresh_quotes_job, "interval", minutes=2, id="quote_snapshot", replace_existing=True)
        _scheduler.add_job(_refresh_news_feed_job, "interval", minutes=NEWS_REFRESH_MINUTES, id="news_refresh", replace_existing=True)
        _scheduler.add_job(lambda: _run_automation_job("market_cycle"), "interval", minutes=MARKET_CYCLE_MINUTES, id="market_cycle", replace_existing=True)
        _scheduler.add_job(lambda: _run_automation_job("alert_cycle"), "interval", minutes=ALERT_CYCLE_MINUTES, id="alert_cycle", replace_existing=True)
        _scheduler.add_job(lambda: _run_automation_job("breadth_cycle"), "interval", minutes=BREADTH_CYCLE_MINUTES, id="breadth_cycle", replace_existing=True)
        _scheduler.add_job(lambda: _run_automation_job("daily_summary"), "cron", hour=AUTOMATION_DAILY_SUMMARY_HOUR, minute=0, id="daily_summary", replace_existing=True)
        _scheduler.add_job(_maintenance_reconcile_job, "interval", seconds=120, id="maintenance_reconcile", replace_existing=True)
        if ENABLE_AUTO_RETRAIN:
            _scheduler.add_job(lambda: _run_automation_job("retrain_cycle"), "interval", hours=RETRAIN_CYCLE_HOURS, id="retrain_cycle", replace_existing=True)
        if ENABLE_AUTONOMOUS_CYCLE:
            _scheduler.add_job(lambda: _run_automation_job("autonomous_cycle"), "interval", hours=AUTONOMOUS_CYCLE_HOURS, id="autonomous_cycle", replace_existing=True)
        # Trailing stop monitor — check every 5 minutes
        _scheduler.add_job(_run_trailing_stop_job, "interval", minutes=5, id="trailing_stop_check", replace_existing=True)
        # Auto-trading — signal-driven paper trading.
        # The job always exists; runtime settings decide whether each cycle acts or skips.
        _scheduler.add_job(
            lambda: _run_automation_job("auto_trading_cycle"),
            "interval",
            minutes=_runtime_auto_trading_cycle_minutes(),
            id="auto_trading_cycle",
            replace_existing=True,
        )
        _scheduler.add_job(
            _sync_auto_trading_schedule_job,
            "interval",
            seconds=60,
            id="auto_trading_schedule_sync",
            replace_existing=True,
        )
        # Smart automation — AI-powered opportunity scanner
        try:
            _scheduler.add_job(_run_smart_cycle_job, "interval", minutes=45, id="smart_cycle", replace_existing=True)
        except Exception:
            pass
        _jobs_registered = True
    scheduler_started = False
    if not _scheduler.running:
        _scheduler.start()
        scheduler_started = True
        log_event(logger, logging.INFO, "scheduler.started", jobs_registered=_jobs_registered, jobs=len(_scheduler.get_jobs()))
    if CONTINUOUS_LEARNING_STARTUP_ENABLED:
        if scheduler_started or _last_continuous_learning_start_result is None:
            _last_continuous_learning_start_result = start_continuous_learning(requested_by="scheduler_startup")
    else:
        _last_continuous_learning_start_result = {
            "attempted": False,
            "accepted": False,
            "reason": "Continuous learning startup is not enabled for this process.",
        }
    return {
        "enabled": True,
        "running": _scheduler.running,
        "blocked": False,
        "runtime_state": _scheduler_runtime_state(),
        "continuous_learning": _last_continuous_learning_start_result,
    }


def stop_scheduler():
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        return {"enabled": BackgroundScheduler is not None, "running": False}
    _scheduler.shutdown(wait=False)
    log_event(logger, logging.INFO, "scheduler.stopped", role=SERVER_ROLE, runner_role=SCHEDULER_RUNNER_ROLE)
    return {"enabled": True, "running": False}


def get_scheduler_status():
    jobs = []
    if _scheduler is not None:
        jobs = [
            {
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in _scheduler.get_jobs()
        ]
    with session_scope() as session:
        recent = session.query(SchedulerRun).order_by(SchedulerRun.ran_at.desc()).limit(10).all()
        history = [
            {
                "job_name": row.job_name,
                "status": row.status,
                "ran_at": row.ran_at.isoformat() if row.ran_at else None,
                "detail": row.detail,
            }
            for row in recent
        ]
    blocked_reason = _scheduler_blocked_reason()
    return {
        "scheduler_enabled": ENABLE_SCHEDULER,
        "scheduler_dependency_ready": BackgroundScheduler is not None,
        "scheduler_running": bool(_scheduler and _scheduler.running),
        "scheduler_startup_enabled": SCHEDULER_ROLE_ALLOWED and ENABLE_SCHEDULER,
        "scheduler_runner_role": SCHEDULER_RUNNER_ROLE,
        "scheduler_role_allowed": can_current_process_run_scheduler(),
        "server_role": SERVER_ROLE,
        "runtime_state": _scheduler_runtime_state(),
        "blocked": blocked_reason is not None,
        "blocked_reason": blocked_reason,
        "jobs_registered": _jobs_registered,
        "jobs_count": len(jobs),
        "jobs": jobs,
        "recent_runs": history,
        "continuous_learning_startup": _last_continuous_learning_start_result,
    }
