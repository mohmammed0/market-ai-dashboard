from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.services.auto_trading_diagnostics import get_latest_auto_trading_cycle_diagnostics
from backend.app.services.kronos_intelligence import get_kronos_batch_cache_snapshot, kronos_status, run_kronos_inference_for_symbol
from backend.app.services.market_readiness import get_latest_market_readiness
from backend.app.services.market_session_intelligence import get_market_session_snapshot


router = APIRouter(prefix="/kronos", tags=["kronos"])


@router.get("/status")
def kronos_runtime_status():
    item = kronos_status()
    if isinstance(item, dict) and "kronos_batch_cache" not in item:
        item["kronos_batch_cache"] = get_kronos_batch_cache_snapshot(include_symbols=False)
    return {
        "status": "ok",
        "item": item,
    }


@router.get("/latest")
def kronos_latest(limit_symbols: int = Query(default=20, ge=1, le=200)):
    latest = get_latest_auto_trading_cycle_diagnostics(
        include_details=False,
        include_model_breakdown=False,
        include_raw=False,
        latest_nonempty=True,
    )
    if latest is None:
        return {"status": "empty", "item": None}

    rows = latest.get("rows") if isinstance(latest.get("rows"), list) else []
    kronos_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kronos_rows.append(
            {
                "symbol": row.get("symbol"),
                "kronos_ready": row.get("kronos_ready"),
                "kronos_score": row.get("kronos_score"),
                "kronos_confidence": row.get("kronos_confidence"),
                "kronos_premarket_score": row.get("kronos_premarket_score"),
                "kronos_opening_score": row.get("kronos_opening_score"),
                "kronos_session_preferred_action": row.get("kronos_session_preferred_action"),
                "kronos_execution_timing_bias": row.get("kronos_execution_timing_bias"),
                "kronos_contribution_to_score": row.get("kronos_contribution_to_score"),
                "session_order_plan": row.get("session_order_plan"),
                "session_state": row.get("session_state"),
            }
        )

    kronos_rows.sort(key=lambda item: float(item.get("kronos_score") or 0.0), reverse=True)
    kronos_rows = kronos_rows[:limit_symbols]

    item = {
        "cycle_id": latest.get("cycle_id"),
        "cycle_started_at": latest.get("cycle_started_at"),
        "cycle_completed_at": latest.get("cycle_completed_at"),
        "kronos": latest.get("kronos") if isinstance(latest.get("kronos"), dict) else {},
        "market_session": latest.get("market_session") if isinstance(latest.get("market_session"), dict) else {},
        "market_readiness": latest.get("market_readiness") if isinstance(latest.get("market_readiness"), dict) else {},
        "shared_batch_cache": get_kronos_batch_cache_snapshot(include_symbols=False),
        "symbols": kronos_rows,
        "count": len(kronos_rows),
    }
    return {"status": "ok", "item": item}


@router.get("/symbol/{symbol}")
def kronos_symbol(
    symbol: str,
    refresh_session: bool = Query(default=False),
    session_state: str | None = Query(default=None),
):
    session_snapshot = get_market_session_snapshot(refresh=refresh_session)
    if session_state:
        normalized_state = str(session_state).strip().lower()
        if normalized_state:
            session_snapshot = dict(session_snapshot)
            session_snapshot["session_state"] = normalized_state
            session_snapshot["session_code"] = normalized_state

    inference = run_kronos_inference_for_symbol(
        symbol,
        session_snapshot=session_snapshot,
    )
    return {
        "status": "ok",
        "item": {
            "symbol": str(symbol or "").strip().upper(),
            "session": session_snapshot,
            "inference": inference,
        },
    }


@router.get("/readiness/latest")
def kronos_readiness_latest():
    payload = get_latest_market_readiness()
    if payload is None:
        return {"status": "empty", "item": None}

    market_readiness = payload.get("market_readiness") if isinstance(payload.get("market_readiness"), dict) else {}
    market_session = payload.get("market_session") if isinstance(payload.get("market_session"), dict) else {}
    kronos_payload = payload.get("kronos") if isinstance(payload.get("kronos"), dict) else {}

    return {
        "status": "ok",
        "item": {
            "cycle_id": payload.get("cycle_id"),
            "cycle_started_at": payload.get("cycle_started_at"),
            "cycle_completed_at": payload.get("cycle_completed_at"),
            "market_session": market_session,
            "market_readiness": market_readiness,
            "kronos": kronos_payload,
            "shared_batch_cache": get_kronos_batch_cache_snapshot(include_symbols=False),
        },
    }
