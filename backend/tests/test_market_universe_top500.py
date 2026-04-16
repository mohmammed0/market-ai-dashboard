from __future__ import annotations

from unittest.mock import patch

from backend.app.db.session import init_db
from backend.app.models import CurrencyReference, MarketUniverseSymbol
from backend.app.services.market_universe import (
    _parse_top_market_cap_page,
    _seed_currency_references,
    list_currency_references,
    resolve_universe_preset,
)
from backend.app.services.storage import session_scope


def test_parse_top_market_cap_page_extracts_us_companies():
    html = """
    <script>
    {"companies":[
      {"symbol":"AAPL","name":"Apple Inc.","rank":3,"marketCap":3820000000000,"country":"US"},
      {"symbol":"MSFT","name":"Microsoft Corporation","rank":4,"marketCap":2760000000000,"country":"US"}
    ]}
    </script>
    """

    items = _parse_top_market_cap_page(html)

    assert len(items) == 2
    assert items[0]["symbol"] == "AAPL"
    assert items[0]["market_cap_rank"] == 3
    assert items[0]["market_cap_currency"] == "USD"


def test_resolve_top_500_preset_orders_by_market_cap_rank():
    init_db(run_migrations=True)
    with session_scope() as session:
        session.query(MarketUniverseSymbol).delete()
        session.add_all(
            [
                MarketUniverseSymbol(
                    symbol="MSFT",
                    security_name="Microsoft",
                    exchange="NASDAQ",
                    market_type="NASDAQ Equity",
                    active=True,
                    market_cap=2_760_000_000_000.0,
                    market_cap_rank=4,
                    market_cap_currency="USD",
                    market_cap_source="companiesmarketcap.org",
                ),
                MarketUniverseSymbol(
                    symbol="AAPL",
                    security_name="Apple",
                    exchange="NASDAQ",
                    market_type="NASDAQ Equity",
                    active=True,
                    market_cap=3_820_000_000_000.0,
                    market_cap_rank=3,
                    market_cap_currency="USD",
                    market_cap_source="companiesmarketcap.org",
                ),
                MarketUniverseSymbol(
                    symbol="SPY",
                    security_name="SPDR S&P 500 ETF Trust",
                    exchange="NYSE Arca",
                    market_type="ETF",
                    is_etf=True,
                    active=True,
                ),
            ]
        )

    with patch("backend.app.services.market_universe.ensure_market_universe", return_value={"status": "ok"}):
        payload = resolve_universe_preset("TOP500", limit=2)

    assert payload["preset"] == "TOP_500_MARKET_CAP"
    assert payload["symbols"] == ["AAPL", "MSFT"]
    assert payload["matched_count"] == 2


def test_list_currency_references_returns_seeded_major_currencies():
    init_db(run_migrations=True)
    with session_scope() as session:
        session.query(CurrencyReference).delete()

    _seed_currency_references()

    with patch("backend.app.services.market_universe.ensure_market_universe", return_value={"status": "ok"}):
        payload = list_currency_references(limit=50, major_only=True)

    codes = {item["code"] for item in payload["items"]}
    assert "USD" in codes
    assert "EUR" in codes
    assert "SAR" not in codes
