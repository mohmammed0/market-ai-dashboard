from fastapi import APIRouter, Query

from backend.app.schemas import MarketTerminalChartRequest, MarketTerminalContextRequest
from backend.app.services.market_terminal import (
    build_market_terminal_bootstrap,
    build_market_terminal_chart,
    build_market_terminal_context,
)


router = APIRouter(prefix="/market/terminal", tags=["market-terminal"])


@router.get("/bootstrap")
def market_terminal_bootstrap(
    symbol: str = Query(default="AAPL"),
    q: str = Query(default=""),
    exchange: str = Query(default="ALL"),
    type: str = Query(default="all"),
    category: str = Query(default="all"),
    limit: int = Query(default=40, ge=1, le=100),
):
    return build_market_terminal_bootstrap(
        symbol=symbol,
        q=q,
        exchange=exchange,
        security_type=type,
        category=category,
        limit=limit,
    )


@router.post("/chart")
def market_terminal_chart(payload: MarketTerminalChartRequest):
    return build_market_terminal_chart(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        range_key=payload.range_key,
        compare_symbols=payload.compare_symbols,
    )


@router.post("/context")
def market_terminal_context(payload: MarketTerminalContextRequest):
    return build_market_terminal_context(
        symbol=payload.symbol,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
