from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.app.services.auto_trading_diagnostics import (
    export_auto_trading_cycle_rows_csv,
    get_auto_trading_cycle_diagnostics,
    get_latest_auto_trading_cycle_diagnostics,
    list_auto_trading_cycle_diagnostics,
)


router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/auto-trading/latest")
def auto_trading_diagnostics_latest(
    include_details: bool = Query(default=False),
    include_model_breakdown: bool = Query(default=False),
    include_raw: bool = Query(default=False),
    row_symbol: str | None = Query(default=None),
    latest_nonempty: bool = Query(default=False),
):
    payload = get_latest_auto_trading_cycle_diagnostics(
        include_details=include_details,
        include_model_breakdown=include_model_breakdown,
        include_raw=include_raw,
        row_symbol=row_symbol,
        latest_nonempty=latest_nonempty,
    )
    if payload is None:
        return {
            "status": "empty",
            "detail": "No auto-trading diagnostics cycles captured yet.",
            "item": None,
        }
    return {
        "status": "ok",
        "item": payload,
    }


@router.get("/auto-trading/cycles")
def auto_trading_diagnostics_cycles(
    limit: int = Query(default=20, ge=1, le=100),
    include_rows: bool = Query(default=False),
    include_details: bool = Query(default=False),
    include_model_breakdown: bool = Query(default=False),
    include_raw: bool = Query(default=False),
    row_symbol: str | None = Query(default=None),
):
    payload = list_auto_trading_cycle_diagnostics(
        limit=limit,
        include_rows=include_rows,
        include_details=include_details,
        include_model_breakdown=include_model_breakdown,
        include_raw=include_raw,
        row_symbol=row_symbol,
    )
    return {
        "status": "ok",
        **payload,
    }


@router.get("/auto-trading/cycles/{cycle_id}/export.csv")
def auto_trading_diagnostics_cycle_export(cycle_id: str):
    payload = get_auto_trading_cycle_diagnostics(
        cycle_id,
        include_details=True,
        include_model_breakdown=True,
        include_raw=False,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Diagnostics cycle not found")
    csv_body = export_auto_trading_cycle_rows_csv(payload)
    filename = f"auto_trading_diagnostics_{cycle_id}.csv"
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/auto-trading/cycles/{cycle_id}")
def auto_trading_diagnostics_cycle(
    cycle_id: str,
    include_details: bool = Query(default=False),
    include_model_breakdown: bool = Query(default=False),
    include_raw: bool = Query(default=False),
    row_symbol: str | None = Query(default=None),
):
    payload = get_auto_trading_cycle_diagnostics(
        cycle_id,
        include_details=include_details,
        include_model_breakdown=include_model_breakdown,
        include_raw=include_raw,
        row_symbol=row_symbol,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Diagnostics cycle not found")
    return {
        "status": "ok",
        "item": payload,
    }
