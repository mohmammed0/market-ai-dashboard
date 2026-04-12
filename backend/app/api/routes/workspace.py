from fastapi import APIRouter, HTTPException

from backend.app.schemas import (
    FavoritesToggleRequest,
    WatchlistCreateRequest,
    WatchlistItemRequest,
    WatchlistUpdateRequest,
    WorkspaceStateRequest,
)
from backend.app.services.workspace_store import (
    add_symbol_to_watchlist,
    create_watchlist,
    delete_watchlist,
    get_workspace_overview,
    initialize_workspace_defaults,
    list_watchlists,
    remove_symbol_from_watchlist,
    toggle_favorite_symbol,
    update_watchlist,
    update_workspace_state,
)


router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/overview")
def workspace_overview():
    return get_workspace_overview()


@router.post("/initialize")
def workspace_initialize():
    return initialize_workspace_defaults()


@router.get("/watchlists")
def workspace_watchlists():
    return {"items": list_watchlists()}


@router.post("/watchlists")
def workspace_create_watchlist(payload: WatchlistCreateRequest):
    try:
        return create_watchlist(payload.name, category=payload.category, color_token=payload.color_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/watchlists/{watchlist_id}")
def workspace_update_watchlist(watchlist_id: int, payload: WatchlistUpdateRequest):
    try:
        return update_watchlist(
            watchlist_id,
            name=payload.name,
            color_token=payload.color_token,
            is_default=payload.is_default,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/watchlists/{watchlist_id}")
def workspace_delete_watchlist(watchlist_id: int):
    try:
        delete_watchlist(watchlist_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/watchlists/{watchlist_id}/items")
def workspace_add_watchlist_item(watchlist_id: int, payload: WatchlistItemRequest):
    try:
        return add_symbol_to_watchlist(watchlist_id, payload.symbol, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/watchlists/{watchlist_id}/items/{symbol}")
def workspace_remove_watchlist_item(watchlist_id: int, symbol: str):
    try:
        return remove_symbol_from_watchlist(watchlist_id, symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/favorites/toggle")
def workspace_toggle_favorite(payload: FavoritesToggleRequest):
    try:
        return toggle_favorite_symbol(payload.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/state")
def workspace_update_state(payload: WorkspaceStateRequest):
    return update_workspace_state(
        active_symbol=payload.active_symbol,
        active_watchlist_id=payload.active_watchlist_id,
        timeframe=payload.timeframe,
        range_key=payload.range_key,
        layout_mode=payload.layout_mode,
        compare_symbols=payload.compare_symbols,
    )
