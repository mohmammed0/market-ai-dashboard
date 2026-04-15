from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path

services_pkg = types.ModuleType("backend.app.services")
services_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "services")]
services_pkg.get_cache = lambda: type(
    "DummyCache",
    (),
    {
        "get": lambda self, key: None,
        "set": lambda self, key, value, ttl_seconds=None: value,
        "get_or_set": lambda self, key, factory, ttl_seconds=None: factory(),
        "delete": lambda self, key: None,
    },
)()
sys.modules.setdefault("backend.app.services", services_pkg)

from backend.app.application.execution.service import (
    _build_trade_intents,
    _validate_cash_only_order,
    create_paper_order,
)
from backend.app.domain.execution.contracts import PositionState, SignalSnapshot


class ExecutionCashOnlyTests(unittest.TestCase):
    def test_sell_signal_without_long_position_does_not_open_short(self):
        signal = SignalSnapshot(
            symbol="AAPL",
            strategy_mode="classic",
            signal="SELL",
            confidence=92.0,
            price=180.0,
            reasoning="take risk off",
            analysis_payload={},
        )

        intents = _build_trade_intents(None, signal, quantity=1)

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].intent, "NONE")

    def test_cash_only_validator_blocks_buy_above_available_cash(self):
        with patch("backend.app.application.execution.service.get_internal_portfolio", return_value={"summary": {"cash_balance": 100.0}}):
            allowed, reason = _validate_cash_only_order(
                side="BUY",
                symbol="AAPL",
                quantity=2,
                estimated_price=60.0,
                fee_amount=1.0,
                current_position=None,
            )

        self.assertFalse(allowed)
        self.assertIn("Cash-only", reason)

    def test_cash_only_validator_blocks_sell_above_held_quantity(self):
        position = PositionState(
            symbol="AAPL",
            strategy_mode="manual",
            side="LONG",
            quantity=3,
            avg_entry_price=100.0,
        )

        allowed, reason = _validate_cash_only_order(
            side="SELL",
            symbol="AAPL",
            quantity=5,
            estimated_price=110.0,
            current_position=position,
        )

        self.assertFalse(allowed)
        self.assertIn("blocks short selling", reason)

    def test_create_paper_order_rejects_sell_without_held_shares(self):
        fake_fill = type(
            "Fill",
            (),
            {
                "fill_price": 100.0,
                "fee_amount": 0.25,
                "is_partial": False,
                "filled_quantity": 1.0,
                "to_notes_str": lambda self: "fill=100",
                "to_audit_dict": lambda self: {"fill_price": 100.0},
            },
        )()

        with patch("backend.app.application.execution.service.is_halted", return_value=False), \
             patch("backend.app.application.execution.service._latest_price", return_value=(100.0, {"bid": 99.5, "ask": 100.5})), \
             patch("backend.app.application.execution.service.compute_fill", return_value=fake_fill), \
             patch("backend.app.application.execution.service.session_scope") as session_scope:
            session_scope.return_value.__enter__.return_value = object()
            repo = type(
                "Repo",
                (),
                {
                    "get_order_by_client_id": lambda self, client_order_id: None,
                    "get_any_open_position_row": lambda self, symbol: None,
                    "append_audit_event": lambda self, event: None,
                },
            )()
            with patch("backend.app.application.execution.service.ExecutionRepository", return_value=repo):
                with self.assertRaisesRegex(ValueError, "Short selling is disabled"):
                    create_paper_order(symbol="AAPL", side="SELL", quantity=1)


if __name__ == "__main__":
    unittest.main()
