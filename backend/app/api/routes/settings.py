from fastapi import APIRouter, HTTPException

from backend.app.schemas.runtime_settings import AlpacaSettingsUpdateRequest
from backend.app.services.runtime_control import get_runtime_control_plane
from backend.app.services.runtime_settings import (
    get_runtime_settings_overview,
    RuntimeSettingsError,
    save_alpaca_runtime_settings,
    test_alpaca_runtime_settings,
)


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/runtime")
def runtime_settings():
    try:
        payload = get_runtime_settings_overview()
        payload["control_plane"] = get_runtime_control_plane()
        return payload
    except RuntimeSettingsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/runtime/alpaca")
def update_alpaca_settings(payload: AlpacaSettingsUpdateRequest):
    try:
        settings = save_alpaca_runtime_settings(
            enabled=payload.enabled,
            provider=payload.provider,
            paper=payload.paper,
            api_key=payload.api_key,
            secret_key=payload.secret_key,
            clear_api_key=payload.clear_api_key,
            clear_secret_key=payload.clear_secret_key,
            url_override=payload.url_override,
            auto_trading_enabled=payload.auto_trading_enabled,
            order_submission_enabled=payload.order_submission_enabled,
            auto_trading_cycle_minutes=payload.auto_trading_cycle_minutes,
        )
        return {
            "saved": True,
            "detail": "Alpaca runtime settings saved.",
            "settings": settings,
        }
    except RuntimeSettingsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/runtime/alpaca/test")
def test_alpaca_settings():
    try:
        return test_alpaca_runtime_settings()
    except RuntimeSettingsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/runtime/auto-trading")
def get_auto_trading_status():
    """Get current auto-trading configuration status."""
    from backend.app.services.runtime_settings import get_auto_trading_config
    try:
        return get_auto_trading_config()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
