from __future__ import annotations

from datetime import datetime

from backend.app.models import Watchlist, WatchlistItem, WorkspaceState
from backend.app.services import get_cache
from backend.app.services.storage import dumps_json, loads_json, session_scope
from core.source_data import normalize_symbol


DEFAULT_WORKSPACE_KEY = "default"
FAVORITES_WATCHLIST_NAME = "المفضلة"
SYSTEM_WATCHLISTS = [
    {
        "name": "المؤشرات الكبرى",
        "category": "indices",
        "color_token": "cyan",
        "symbols": ["SPY", "QQQ", "DIA", "IWM"],
    },
    {
        "name": "قطاع التقنية",
        "category": "sector",
        "color_token": "blue",
        "symbols": ["AAPL", "MSFT", "NVDA", "AVGO", "AMD"],
    },
    {
        "name": "قادة الذكاء الاصطناعي",
        "category": "ai",
        "color_token": "teal",
        "symbols": ["NVDA", "AMD", "MSFT", "META", "GOOGL"],
    },
]


def _cache():
    return get_cache()


def _invalidate_workspace_cache() -> None:
    _cache().delete_prefix("workspace:")


def _serialize_watchlist_item(item: WatchlistItem) -> dict:
    return {
        "id": item.id,
        "symbol": item.symbol,
        "display_order": item.display_order,
        "notes": item.notes,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_watchlist(watchlist: Watchlist, items: list[WatchlistItem]) -> dict:
    sorted_items = sorted(items, key=lambda row: (row.display_order, row.symbol))
    return {
        "id": watchlist.id,
        "name": watchlist.name,
        "category": watchlist.category,
        "color_token": watchlist.color_token,
        "is_system": bool(watchlist.is_system),
        "is_default": bool(watchlist.is_default),
        "count": len(sorted_items),
        "symbols": [row.symbol for row in sorted_items],
        "items": [_serialize_watchlist_item(row) for row in sorted_items],
        "updated_at": watchlist.updated_at.isoformat() if watchlist.updated_at else None,
    }


def _serialize_workspace_state(state: WorkspaceState | None) -> dict:
    if state is None:
        return {
            "workspace_key": DEFAULT_WORKSPACE_KEY,
            "active_symbol": "AAPL",
            "active_watchlist_id": None,
            "timeframe": "1D",
            "range_key": "3M",
            "layout_mode": "terminal",
            "compare_symbols": [],
            "updated_at": None,
        }
    return {
        "workspace_key": state.workspace_key,
        "active_symbol": state.active_symbol or "AAPL",
        "active_watchlist_id": state.active_watchlist_id,
        "timeframe": state.timeframe or "1D",
        "range_key": state.range_key or "3M",
        "layout_mode": state.layout_mode or "terminal",
        "compare_symbols": loads_json(state.compare_symbols_json, default=[]),
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _ensure_default_watchlists() -> None:
    with session_scope() as session:
        favorites = session.query(Watchlist).filter(Watchlist.name == FAVORITES_WATCHLIST_NAME).first()
        if favorites is None:
            favorites = Watchlist(
                name=FAVORITES_WATCHLIST_NAME,
                category="favorites",
                color_token="amber",
                is_system=False,
                is_default=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(favorites)
            session.flush()

        existing = {row.name: row for row in session.query(Watchlist).filter(Watchlist.is_system.is_(True)).all()}
        for watchlist_def in SYSTEM_WATCHLISTS:
            row = existing.get(watchlist_def["name"])
            if row is None:
                row = Watchlist(
                    name=watchlist_def["name"],
                    category=watchlist_def["category"],
                    color_token=watchlist_def["color_token"],
                    is_system=True,
                    is_default=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(row)
                session.flush()
            row.updated_at = datetime.utcnow()
            current_symbols = {
                item.symbol: item
                for item in session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == row.id).all()
            }
            for index, symbol in enumerate(watchlist_def["symbols"]):
                normalized = normalize_symbol(symbol)
                existing_item = current_symbols.get(normalized)
                if existing_item is None:
                    session.add(WatchlistItem(
                        watchlist_id=row.id,
                        symbol=normalized,
                        display_order=index,
                        created_at=datetime.utcnow(),
                    ))

        workspace = session.query(WorkspaceState).filter(WorkspaceState.workspace_key == DEFAULT_WORKSPACE_KEY).first()
        if workspace is None:
            session.add(WorkspaceState(
                workspace_key=DEFAULT_WORKSPACE_KEY,
                active_symbol="AAPL",
                active_watchlist_id=favorites.id,
                timeframe="1D",
                range_key="3M",
                layout_mode="terminal",
                compare_symbols_json=dumps_json([]),
                updated_at=datetime.utcnow(),
            ))


def initialize_workspace_defaults() -> dict:
    _ensure_default_watchlists()
    _invalidate_workspace_cache()
    return get_workspace_overview()


def list_watchlists() -> list[dict]:
    def factory():
        with session_scope() as session:
            watchlists = session.query(Watchlist).order_by(Watchlist.is_default.desc(), Watchlist.is_system.desc(), Watchlist.name.asc()).all()
            items = session.query(WatchlistItem).order_by(WatchlistItem.display_order.asc(), WatchlistItem.symbol.asc()).all()
            items_by_watchlist: dict[int, list[WatchlistItem]] = {}
            for item in items:
                items_by_watchlist.setdefault(item.watchlist_id, []).append(item)
            return [_serialize_watchlist(row, items_by_watchlist.get(row.id, [])) for row in watchlists]

    return _cache().get_or_set("workspace:watchlists", factory, ttl_seconds=30)


def get_workspace_overview() -> dict:
    def factory():
        with session_scope() as session:
            workspace = session.query(WorkspaceState).filter(WorkspaceState.workspace_key == DEFAULT_WORKSPACE_KEY).first()
        watchlists = list_watchlists()
        workspace_payload = _serialize_workspace_state(workspace)
        active_watchlist = next((item for item in watchlists if item["id"] == workspace_payload["active_watchlist_id"]), None)
        favorites = next((item for item in watchlists if item["name"] == FAVORITES_WATCHLIST_NAME), None)
        return {
            "initialized": bool(workspace is not None or watchlists),
            "workspace": workspace_payload,
            "watchlists": watchlists,
            "favorites_watchlist_id": favorites["id"] if favorites else None,
            "active_watchlist": active_watchlist,
        }

    return _cache().get_or_set("workspace:overview", factory, ttl_seconds=15)


def create_watchlist(name: str, category: str = "custom", color_token: str | None = None) -> dict:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("Watchlist name is required.")
    _ensure_default_watchlists()
    with session_scope() as session:
        existing = session.query(Watchlist).filter(Watchlist.name == normalized_name).first()
        if existing is not None:
            raise ValueError("Watchlist name already exists.")
        row = Watchlist(
            name=normalized_name,
            category=str(category or "custom").strip().lower() or "custom",
            color_token=color_token,
            is_system=False,
            is_default=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        payload = _serialize_watchlist(row, [])
    _invalidate_workspace_cache()
    return payload


def update_watchlist(watchlist_id: int, *, name: str | None = None, color_token: str | None = None, is_default: bool | None = None) -> dict:
    _ensure_default_watchlists()
    with session_scope() as session:
        row = session.query(Watchlist).filter(Watchlist.id == int(watchlist_id)).first()
        if row is None:
            raise ValueError("Watchlist not found.")
        if row.is_system:
            raise ValueError("System watchlists cannot be renamed.")
        if name is not None:
            row.name = str(name).strip() or row.name
        if color_token is not None:
            row.color_token = color_token or None
        if is_default is not None:
            if is_default:
                session.query(Watchlist).update({Watchlist.is_default: False})
            row.is_default = bool(is_default)
        row.updated_at = datetime.utcnow()
        items = session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == row.id).all()
        payload = _serialize_watchlist(row, items)
    _invalidate_workspace_cache()
    return payload


def delete_watchlist(watchlist_id: int) -> None:
    _ensure_default_watchlists()
    with session_scope() as session:
        row = session.query(Watchlist).filter(Watchlist.id == int(watchlist_id)).first()
        if row is None:
            return
        if row.is_system or row.name == FAVORITES_WATCHLIST_NAME:
            raise ValueError("Default or system watchlists cannot be deleted.")
        session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == row.id).delete()
        session.delete(row)
    _invalidate_workspace_cache()


def add_symbol_to_watchlist(watchlist_id: int, symbol: str, notes: str | None = None) -> dict:
    normalized_symbol = normalize_symbol(symbol)
    if not normalized_symbol:
        raise ValueError("Symbol is required.")
    _ensure_default_watchlists()
    with session_scope() as session:
        row = session.query(Watchlist).filter(Watchlist.id == int(watchlist_id)).first()
        if row is None:
            raise ValueError("Watchlist not found.")
        existing = session.query(WatchlistItem).filter(
            WatchlistItem.watchlist_id == row.id,
            WatchlistItem.symbol == normalized_symbol,
        ).first()
        if existing is None:
            display_order = (session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == row.id).count()) + 1
            session.add(WatchlistItem(
                watchlist_id=row.id,
                symbol=normalized_symbol,
                display_order=display_order,
                notes=notes,
                created_at=datetime.utcnow(),
            ))
        row.updated_at = datetime.utcnow()
        session.flush()
        items = session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == row.id).all()
        payload = _serialize_watchlist(row, items)
    _invalidate_workspace_cache()
    return payload


def remove_symbol_from_watchlist(watchlist_id: int, symbol: str) -> dict:
    normalized_symbol = normalize_symbol(symbol)
    _ensure_default_watchlists()
    with session_scope() as session:
        row = session.query(Watchlist).filter(Watchlist.id == int(watchlist_id)).first()
        if row is None:
            raise ValueError("Watchlist not found.")
        session.query(WatchlistItem).filter(
            WatchlistItem.watchlist_id == row.id,
            WatchlistItem.symbol == normalized_symbol,
        ).delete()
        row.updated_at = datetime.utcnow()
        items = session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == row.id).all()
        payload = _serialize_watchlist(row, items)
    _invalidate_workspace_cache()
    return payload


def toggle_favorite_symbol(symbol: str) -> dict:
    normalized_symbol = normalize_symbol(symbol)
    _ensure_default_watchlists()
    with session_scope() as session:
        favorites = session.query(Watchlist).filter(Watchlist.name == FAVORITES_WATCHLIST_NAME).first()
        if favorites is None:
            raise ValueError("Favorites watchlist unavailable.")
        existing = session.query(WatchlistItem).filter(
            WatchlistItem.watchlist_id == favorites.id,
            WatchlistItem.symbol == normalized_symbol,
        ).first()
        if existing is None:
            display_order = (session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == favorites.id).count()) + 1
            session.add(WatchlistItem(
                watchlist_id=favorites.id,
                symbol=normalized_symbol,
                display_order=display_order,
                created_at=datetime.utcnow(),
            ))
            action = "added"
        else:
            session.delete(existing)
            action = "removed"
        favorites.updated_at = datetime.utcnow()
        session.flush()
        items = session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == favorites.id).all()
        payload = {
            "action": action,
            "watchlist": _serialize_watchlist(favorites, items),
            "symbol": normalized_symbol,
        }
    _invalidate_workspace_cache()
    return payload


def update_workspace_state(
    *,
    active_symbol: str | None = None,
    active_watchlist_id: int | None = None,
    timeframe: str | None = None,
    range_key: str | None = None,
    layout_mode: str | None = None,
    compare_symbols: list[str] | None = None,
) -> dict:
    _ensure_default_watchlists()
    with session_scope() as session:
        row = session.query(WorkspaceState).filter(WorkspaceState.workspace_key == DEFAULT_WORKSPACE_KEY).first()
        if row is None:
            row = WorkspaceState(workspace_key=DEFAULT_WORKSPACE_KEY, updated_at=datetime.utcnow())
            session.add(row)
        if active_symbol is not None:
            row.active_symbol = normalize_symbol(active_symbol) if active_symbol else None
        if active_watchlist_id is not None:
            row.active_watchlist_id = active_watchlist_id
        if timeframe:
            row.timeframe = str(timeframe).strip().upper()
        if range_key:
            row.range_key = str(range_key).strip().upper()
        if layout_mode:
            row.layout_mode = str(layout_mode).strip().lower()
        if compare_symbols is not None:
            normalized = [normalize_symbol(symbol) for symbol in compare_symbols if str(symbol).strip()]
            normalized = [symbol for index, symbol in enumerate(normalized) if symbol not in normalized[:index]]
            row.compare_symbols_json = dumps_json(normalized[:4])
        row.updated_at = datetime.utcnow()
        session.flush()
        payload = _serialize_workspace_state(row)
    _invalidate_workspace_cache()
    return payload
