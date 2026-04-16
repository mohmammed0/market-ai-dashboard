from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

from backend.app.application.execution.service import (
    _build_trade_intents,
    _validate_cash_only_order,
    create_paper_order,
    refresh_signals,
)
from backend.app.domain.execution.contracts import PositionState, SignalSnapshot
from backend.app.services import scheduler_runtime


class ExecutionCashOnlyTests(unittest.TestCase):
    def test_refresh_signals_uses_per_symbol_quantity_map(self):
        signal_a = SignalSnapshot(
            symbol="AAPL",
            strategy_mode="classic",
            signal="BUY",
            confidence=90.0,
            price=180.0,
            reasoning="trend",
            analysis_payload={},
        )
        signal_b = SignalSnapshot(
            symbol="MSFT",
            strategy_mode="classic",
            signal="BUY",
            confidence=88.0,
            price=410.0,
            reasoning="momentum",
            analysis_payload={},
        )
        analyzed = [
            {"symbol": "AAPL", "result": {}, "signal_snapshot": signal_a, "error": None},
            {"symbol": "MSFT", "result": {}, "signal_snapshot": signal_b, "error": None},
        ]
        recorded_quantities: list[float] = []

        class _Repo:
            def latest_signal(self, symbol, mode):
                return None

            def append_signal(self, record):
                return None

            def append_alert(self, record):
                return None

            def append_audit_event(self, record):
                return None

            def get_open_position_row(self, symbol, mode):
                return None

        with patch("backend.app.application.execution.service.is_halted", return_value=False), \
             patch("backend.app.application.execution.service._build_quote_lookup", return_value={}), \
             patch("backend.app.application.execution.service._collect_symbol_analyses", return_value=(analyzed, 2)), \
             patch("backend.app.application.execution.service.ExecutionRepository", return_value=_Repo()), \
             patch("backend.app.application.execution.service._record_signal_alerts", return_value=None), \
             patch("backend.app.application.execution.service.publish_event", return_value=None), \
             patch("backend.app.application.execution.service.emit_counter", return_value=None), \
             patch("backend.app.application.execution.service.get_internal_portfolio", return_value={}), \
             patch("backend.app.application.execution.service.get_alert_history", return_value={}), \
             patch("backend.app.application.execution.service.get_signal_history", return_value={}), \
             patch("backend.app.application.execution.service.session_scope") as session_scope, \
             patch("backend.app.application.execution.service._apply_trade_intent") as apply_trade_intent:
            session_scope.return_value.__enter__.return_value = object()

            def _capture(repo, current_row, intent, correlation_id=None, signal_id=None):
                recorded_quantities.append(intent.quantity)

            apply_trade_intent.side_effect = _capture

            result = refresh_signals(
                symbols=["AAPL", "MSFT"],
                auto_execute=True,
                quantity=1.0,
                quantity_map={"AAPL": 3.0, "MSFT": 7.0},
            )

        self.assertEqual(result["items"][0]["symbol"], "AAPL")
        self.assertEqual(result["items"][1]["symbol"], "MSFT")
        self.assertEqual(recorded_quantities, [3.0, 7.0])

    def test_scheduler_auto_trading_job_uses_runtime_preset(self):
        with patch("backend.app.services.runtime_settings.get_auto_trading_config", return_value={"universe_preset": "TOP_500_MARKET_CAP"}), \
             patch("backend.app.services.scheduler_runtime.run_automation_job", return_value={"status": "completed", "detail": "ok"}) as run_job, \
             patch("backend.app.services.scheduler_runtime._record_job", return_value=None):
            scheduler_runtime._run_automation_job("auto_trading_cycle")

        run_job.assert_called_once_with(
            job_name="auto_trading_cycle",
            dry_run=False,
            preset="TOP_500_MARKET_CAP",
        )

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

    def test_cash_only_validator_allows_covering_short_even_without_cash(self):
        position = PositionState(
            symbol="AAPL",
            strategy_mode="manual",
            side="SHORT",
            quantity=3,
            avg_entry_price=100.0,
        )

        with patch("backend.app.application.execution.service.get_internal_portfolio", return_value={"summary": {"cash_balance": 0.0}}):
            allowed, reason = _validate_cash_only_order(
                side="BUY",
                symbol="AAPL",
                quantity=3,
                estimated_price=110.0,
                fee_amount=0.0,
                current_position=position,
            )

        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_sell_signal_opens_short_when_margin_enabled(self):
        signal = SignalSnapshot(
            symbol="AAPL",
            strategy_mode="classic",
            signal="SELL",
            confidence=92.0,
            price=180.0,
            reasoning="trend reversal",
            analysis_payload={},
        )

        with patch("backend.app.application.execution.service.get_broker_guardrails", return_value={"trading_mode": "margin"}):
            intents = _build_trade_intents(None, signal, quantity=1)

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].intent, "OPEN_SHORT")

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
