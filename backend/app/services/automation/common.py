"""Shared primitives for automation cycles.

This module holds reusable helpers used by orchestration and cycle-specific
modules so automation behavior can be split without changing runtime semantics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from backend.app.application.model_lifecycle.service import (
    promote_model_run,
    review_model_promotion,
)
from backend.app.config import (
    AUTOMATION_DEFAULT_PRESET,
    AUTONOMOUS_HISTORY_LOOKBACK_DAYS,
)
from backend.app.core.date_defaults import analysis_window_iso, training_window_iso
from backend.app.models import AutomationArtifact, AutomationRun, MarketUniverseSymbol
from backend.app.services.continuous_learning import get_continuous_learning_runtime_snapshot
from backend.app.services.market_data import SOURCE_DIR, load_history
from backend.app.services.signal_runtime import build_smart_analysis
from backend.app.services.storage import dumps_json, session_scope


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
    return analysis_window_iso()


def _training_window() -> tuple[str, str]:
    return training_window_iso()


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


def _build_ranked_candidates(
    symbols: list[str],
    start_date: str,
    end_date: str,
    include_dl: bool = True,
    include_ensemble: bool = True,
) -> list[dict]:
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
