from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.services.broker.alpaca import AlpacaBrokerProvider


class DummyMarketOrderRequest:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class DummyTradingClient:
    def __init__(self):
        self.submitted = []

    def get_account(self):
        return SimpleNamespace(cash=1000.0, buying_power=5000.0)

    def get_all_positions(self):
        return []

    def submit_order(self, order_data):
        self.submitted.append(order_data)
        return SimpleNamespace(
            id="ord-1",
            client_order_id="client-1",
            symbol=order_data.kwargs["symbol"],
            side=order_data.kwargs["side"],
            order_type="market",
            status="accepted",
            qty=order_data.kwargs["qty"],
            filled_qty=0,
            filled_avg_price=None,
            submitted_at=None,
            updated_at=None,
        )


class DummyCache:
    def delete(self, key):
        return None


class BrokerControlTests(unittest.TestCase):
    def test_margin_mode_allows_sell_without_held_long(self):
        provider = AlpacaBrokerProvider()
        client = DummyTradingClient()

        with patch("backend.app.services.broker.alpaca.get_alpaca_runtime_config", return_value={
            "enabled": True,
            "api_key": "key",
            "secret_key": "secret",
            "paper": True,
            "url_override": "",
            "order_submission_enabled": True,
            "live_execution_enabled": False,
            "trading_mode": "margin",
        }), \
             patch.object(provider, "_client", return_value=(client, None)), \
             patch("backend.app.services.broker.alpaca.OrderSide", SimpleNamespace(BUY="buy", SELL="sell")), \
             patch("backend.app.services.broker.alpaca.TimeInForce", SimpleNamespace(DAY="day", GTC="gtc")), \
             patch("backend.app.services.broker.alpaca.MarketOrderRequest", DummyMarketOrderRequest), \
             patch("backend.app.services.broker.alpaca.get_cache", return_value=DummyCache()):
            result = provider.submit_order(symbol="AAPL", qty=2, side="SELL", estimated_price=100.0)

        self.assertTrue(result["ok"])
        self.assertEqual(len(client.submitted), 1)

    def test_liquidation_flattens_long_and_short_positions(self):
        provider = AlpacaBrokerProvider()
        client = SimpleNamespace(
            get_orders=lambda *args, **kwargs: [],
            get_all_positions=lambda: [
                SimpleNamespace(symbol="AAPL", side="PositionSide.LONG", qty=3, current_price=100.0),
                SimpleNamespace(symbol="TSLA", side="PositionSide.SHORT", qty=2, current_price=200.0),
            ],
        )
        submitted = []

        def fake_submit_order(**kwargs):
            submitted.append(kwargs)
            return {"ok": True, "order": {"id": f"ord-{len(submitted)}"}}

        with patch("backend.app.services.broker.alpaca.get_alpaca_runtime_config", return_value={
            "enabled": True,
            "api_key": "key",
            "secret_key": "secret",
            "paper": True,
            "url_override": "",
            "order_submission_enabled": True,
            "live_execution_enabled": False,
            "trading_mode": "cash",
        }), \
             patch.object(provider, "_client", return_value=(client, None)), \
             patch.object(provider, "submit_order", side_effect=fake_submit_order), \
             patch("backend.app.services.broker.alpaca.get_cache", return_value=DummyCache()):
            result = provider.liquidate_positions(cancel_open_orders=True)

        self.assertTrue(result["ok"])
        self.assertEqual(len(submitted), 2)
        self.assertEqual(submitted[0]["side"], "SELL")
        self.assertEqual(submitted[1]["side"], "BUY")


if __name__ == "__main__":
    unittest.main()
