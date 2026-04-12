"""Celery Application — Live task worker definition.

This module defines the Celery application and registered tasks.
When Celery + Redis are available, tasks are dispatched through the broker.
When unavailable, the orchestration_gateway falls back to in-process execution.

Usage (worker):
    celery -A backend.app.services.celery_app worker --loglevel=info

Usage (beat scheduler, optional):
    celery -A backend.app.services.celery_app beat --loglevel=info
"""

from __future__ import annotations

import logging
from typing import Any

_celery_available = False
_app = None

try:
    from celery import Celery
    _celery_available = True
except ImportError:
    pass

from backend.app.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND


def get_celery_app():
    """Get or create the Celery application singleton.

    Returns None if celery is not installed or not configured.
    """
    global _app
    if not _celery_available or not CELERY_BROKER_URL:
        return None
    if _app is not None:
        return _app

    kwargs: dict[str, Any] = {
        "broker": CELERY_BROKER_URL,
    }
    if CELERY_RESULT_BACKEND:
        kwargs["backend"] = CELERY_RESULT_BACKEND

    _app = Celery("market_ai", **kwargs)
    _app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        # Short tasks should not take more than 5 minutes
        task_soft_time_limit=270,
        task_time_limit=300,
    )

    # Register tasks
    _register_tasks(_app)
    return _app


def _register_tasks(app):
    """Register all Celery tasks on the app instance."""

    @app.task(name="tasks.quote_snapshot", bind=True, max_retries=2)
    def task_quote_snapshot(self, **kwargs):
        """Fetch quote snapshots for configured symbols."""
        try:
            from backend.app.services.market_data import fetch_quote_snapshots
            from backend.app.config import DEFAULT_SAMPLE_SYMBOLS
            symbols = kwargs.get("symbols", DEFAULT_SAMPLE_SYMBOLS)
            result = fetch_quote_snapshots(symbols)
            return {"status": "ok", "snapshots": len(result.get("items", [])), "backend": "celery"}
        except Exception as exc:
            raise self.retry(exc=exc, countdown=10)

    @app.task(name="tasks.maintenance_reconcile", bind=True, max_retries=1)
    def task_maintenance_reconcile(self, **kwargs):
        """Reconcile stale background and training jobs."""
        try:
            from backend.app.services.background_jobs import reconcile_stale_jobs
            from backend.app.application.model_lifecycle.training_jobs import reconcile_stale_training_jobs
            return {
                "bg_jobs_reconciled": reconcile_stale_jobs(),
                "training_jobs_reconciled": reconcile_stale_training_jobs(),
                "backend": "celery",
            }
        except Exception as exc:
            raise self.retry(exc=exc, countdown=5)


# Auto-create the app if configured (allows `celery -A backend.app.services.celery_app worker`)
app = get_celery_app()
