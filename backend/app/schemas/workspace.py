from pydantic import BaseModel, Field


class WatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="custom")
    color_token: str | None = Field(default=None, max_length=24)


class WatchlistUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    color_token: str | None = Field(default=None, max_length=24)
    is_default: bool | None = None


class WatchlistItemRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    notes: str | None = None


class FavoritesToggleRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)


class WorkspaceStateRequest(BaseModel):
    active_symbol: str | None = Field(default=None, max_length=20)
    active_watchlist_id: int | None = None
    timeframe: str | None = Field(default=None, max_length=16)
    range_key: str | None = Field(default=None, max_length=16)
    layout_mode: str | None = Field(default=None, max_length=24)
    compare_symbols: list[str] = Field(default_factory=list)
