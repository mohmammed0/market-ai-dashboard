from __future__ import annotations

from datetime import datetime, UTC
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.app.api.routes.health as health_route
from backend.app.application.portfolio.service import build_portfolio_snapshot_payload
from backend.app.domain.portfolio.contracts import (
    PortfolioSnapshot,
    PortfolioSnapshotV1,
    PortfolioViewSummary,
)
from backend.app.schemas import AIStatus
from backend.app.main import create_app


class ApiContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.auth_enabled_patcher = patch("backend.app.main.AUTH_ENABLED", False)
        cls.startup_patcher = patch("backend.app.main._startup_application_services", return_value=None)
        cls.stop_scheduler_patcher = patch("backend.app.main.stop_scheduler", return_value=None)
        cls.auth_enabled_patcher.start()
        cls.startup_patcher.start()
        cls.stop_scheduler_patcher.start()
        cls.client_cm = TestClient(create_app())
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)
        cls.stop_scheduler_patcher.stop()
        cls.startup_patcher.stop()
        cls.auth_enabled_patcher.stop()

    def test_auth_status_shape(self):
        response = self.client.get("/auth/status")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("auth_enabled", payload)
        self.assertIn("detail", payload)
        self.assertIn("warnings", payload)
        self.assertIsInstance(payload["warnings"], list)

    def test_health_endpoint_uses_cached_context(self):
        fake_context = {
            "process": {"server_role": "all"},
            "orchestration": {"scheduler": {"runtime_state": "disabled"}},
            "broker_runtime": {"provider": "none"},
            "cache": {"provider": "in_memory"},
            "orchestration_topology": {"status": "ok"},
            "environment_bootstrap": {"mode": "test"},
        }
        fake_stack = {"database": "active", "_summary": {"active": 1}}
        health_route._cached_health_context = None
        health_route._cached_health_context_expires_at = 0.0
        health_route._cached_stack_payload = None
        health_route._cached_stack_expires_at = 0.0
        with patch("backend.app.api.routes.health._build_health_context", return_value=fake_context) as build_context, patch(
            "backend.app.api.routes.health._build_stack_summary", return_value=fake_stack
        ) as build_stack:
            first = self.client.get("/health")
            second = self.client.get("/health")

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(build_context.call_count, 1)
        self.assertEqual(build_stack.call_count, 1)
        self.assertEqual(first.json()["process"]["server_role"], "all")
        self.assertEqual(second.json()["live_stack"]["database"], "active")

    def test_portfolio_snapshot_contract(self):
        payload = PortfolioSnapshotV1(
            generated_at=datetime.now(UTC),
            active_source="internal_paper",
            source_type="internal",
            source_label="Internal Simulated Paper",
            broker_connected=False,
            summary=PortfolioViewSummary(
                active_source="internal_paper",
                provider="internal",
                connected=False,
                mode="paper",
                open_positions=1,
                open_orders=0,
                total_market_value=1500.0,
                invested_cost=1400.0,
                cash_balance=98500.0,
                total_equity=100000.0,
                portfolio_value=100000.0,
                total_unrealized_pnl=100.0,
                total_realized_pnl=25.0,
                total_trades=2,
                starting_cash=100000.0,
                win_rate_pct=50.0,
            ),
            positions=[],
            items=[],
            orders=[],
            open_orders=[],
            trades=[],
            broker_status={"provider": "none", "connected": False},
            broker_account=None,
            source_summaries=[],
            canonical_snapshot=PortfolioSnapshot(
                generated_at=datetime.now(UTC),
                positions=[],
                sources=[],
                total_market_value=1500.0,
                total_unrealized_pnl=100.0,
            ),
        )
        with patch("backend.app.api.routes.portfolio.build_portfolio_snapshot_payload", return_value=payload):
            response = self.client.get("/api/portfolio/snapshot")

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["contract_version"], "v1")
        self.assertEqual(data["active_source"], "internal_paper")
        self.assertEqual(data["source_type"], "internal")
        self.assertEqual(data["source_label"], "Internal Simulated Paper")
        self.assertIn("summary", data)
        self.assertIn("positions", data)
        self.assertIn("orders", data)
        self.assertIn("trades", data)
        self.assertEqual(data["summary"]["portfolio_value"], 100000.0)

    def test_ai_status_contract(self):
        response = self.client.get("/api/ai/status")
        self.assertEqual(response.status_code, 200, response.text)
        payload = AIStatus.model_validate(response.json())
        self.assertTrue(hasattr(payload, "effective_status"))
        self.assertTrue(hasattr(payload, "ollama"))

    def test_news_refresh_route_shape(self):
        fake_result = {
            "symbols": ["AAPL", "MSFT"],
            "per_symbol_limit": 3,
            "fetched": 6,
            "inserted": 4,
            "skipped": 2,
            "errors": [],
            "items_by_symbol": [
                {"symbol": "AAPL", "fetched": 3, "inserted": 2, "skipped": 1, "overall_sentiment": "POSITIVE"},
                {"symbol": "MSFT", "fetched": 3, "inserted": 2, "skipped": 1, "overall_sentiment": "NEUTRAL"},
            ],
        }
        with patch("backend.app.api.routes.ai.refresh_news_feed", return_value=fake_result):
            response = self.client.post("/api/ai/news/refresh?symbols=AAPL,MSFT&per_symbol_limit=3")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["symbols"], ["AAPL", "MSFT"])
        self.assertEqual(payload["inserted"], 4)
        self.assertEqual(payload["skipped"], 2)
        self.assertEqual(len(payload["items_by_symbol"]), 2)

    def test_dashboard_lite_contract(self):
        response = self.client.get("/api/dashboard/lite")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("generated_at", payload)
        self.assertIn("ai_status", payload)
        self.assertIn("portfolio_snapshot", payload)
        self.assertIn("market_overview", payload)
        self.assertIn("signals", payload)
        self.assertIn("opportunities", payload)
        self.assertIn("product_scope", payload)
        self.assertIn("auto_trading", payload)
        self.assertIn("automation", payload)
        self.assertIn("telegram", payload)
        self.assertIn("ml_enabled", payload["product_scope"])
        self.assertIn("dl_enabled", payload["product_scope"])
        self.assertIn("lightweight_experiment_mode", payload["product_scope"])

    def test_metrics_otel_contract(self):
        response = self.client.get("/api/metrics/otel")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("otel", payload)
        self.assertIn("enabled", payload["otel"])
        self.assertIn("runtime", payload["otel"])

    def test_signal_surface_uses_experiment_dl_flag(self):
        fake_signal = {
            "symbol": "AAPL",
            "mode": "ensemble",
            "signal": "BUY",
            "confidence": 78.0,
            "price": 180.5,
            "reasoning": "cached signal",
            "start_date": "2026-03-18",
            "end_date": "2026-04-17",
        }
        with patch(
            "backend.app.api.routes.intelligence.get_cached_signal_view",
            return_value=fake_signal,
        ) as get_cached_signal_view, patch(
            "backend.app.api.routes.intelligence.build_smart_analysis",
            side_effect=AssertionError("signal route should not run heavy analysis"),
        ):
            response = self.client.get("/api/intelligence/signal/AAPL")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["signal"], "BUY")
        self.assertEqual(payload["confidence"], 78.0)
        get_cached_signal_view.assert_called_once_with("AAPL", mode="ensemble")

    def test_signal_surface_returns_503_when_cache_is_missing(self):
        with patch("backend.app.api.routes.intelligence.get_cached_signal_view", return_value=None), patch(
            "backend.app.api.routes.intelligence.warm_signal_cache_for_symbol",
            return_value=None,
        ) as warm_signal_cache_for_symbol:
            response = self.client.get("/api/intelligence/signal/AAPL")

        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("Signal cache is not ready", response.text)
        warm_signal_cache_for_symbol.assert_called_once_with("AAPL")

    def test_signal_surface_warms_cache_when_symbol_is_missing(self):
        fake_signal = {
            "symbol": "AAPL",
            "mode": "ensemble",
            "signal": "BUY",
            "confidence": 77.0,
            "price": 181.5,
            "reasoning": "warmed signal",
            "start_date": "2026-03-18",
            "end_date": "2026-04-17",
        }
        with patch(
            "backend.app.api.routes.intelligence.get_cached_signal_view",
            side_effect=[None, fake_signal],
        ) as get_cached_signal_view, patch(
            "backend.app.api.routes.intelligence.warm_signal_cache_for_symbol",
            return_value={"symbol": "AAPL"},
        ) as warm_signal_cache_for_symbol:
            response = self.client.get("/api/intelligence/signal/AAPL")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["signal"], "BUY")
        self.assertEqual(payload["confidence"], 77.0)
        self.assertEqual(get_cached_signal_view.call_count, 2)
        warm_signal_cache_for_symbol.assert_called_once_with("AAPL")

    def test_portfolio_snapshot_prefers_internal_when_broker_is_connected_but_internal_book_remains_active(self):
        canonical_snapshot = PortfolioSnapshot(
            generated_at=datetime.now(UTC),
            positions=[],
            sources=[],
            total_market_value=0.0,
            total_unrealized_pnl=0.0,
        )
        internal_portfolio = {
            "items": [
                {
                    "symbol": "AAPL",
                    "side": "LONG",
                    "quantity": 2,
                    "avg_entry_price": 180.0,
                    "current_price": 181.5,
                    "market_value": 363.0,
                    "unrealized_pnl": 3.0,
                    "realized_pnl": 0.0,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ],
            "summary": {
                "open_positions": 1,
                "invested_cost": 360.0,
                "cash_balance": 99640.0,
                "total_equity": 100003.0,
                "portfolio_value": 100003.0,
                "total_market_value": 363.0,
                "total_unrealized_pnl": 3.0,
                "total_realized_pnl": 0.0,
                "total_trades": 1,
                "starting_cash": 100000.0,
                "win_rate_pct": 100.0,
            },
        }
        broker_summary = {
            "connected": True,
            "paper": True,
            "provider": "alpaca",
            "mode": "paper",
            "positions": [],
            "orders": [],
            "account": {"cash": 100000.0, "equity": 100000.0, "portfolio_value": 100000.0},
        }
        with patch("backend.app.application.portfolio.service.get_internal_portfolio", return_value=internal_portfolio), patch(
            "backend.app.application.portfolio.service.get_broker_summary", return_value=broker_summary
        ), patch("backend.app.application.portfolio.service.list_paper_orders", return_value={"items": []}), patch(
            "backend.app.application.portfolio.service.get_trade_history",
            return_value={"items": [{"symbol": "AAPL", "side": "BUY", "quantity": 2, "price": 180.0}]},
        ), patch("backend.app.application.portfolio.service.load_symbol_profiles", return_value={}), patch(
            "backend.app.application.portfolio.service.build_canonical_portfolio_snapshot",
            return_value=canonical_snapshot,
        ), patch(
            "backend.app.application.execution.service.sync_internal_positions_from_broker",
            return_value={"count": 0},
        ):
            payload = build_portfolio_snapshot_payload()

        self.assertEqual(payload.active_source, "internal_paper")
        self.assertEqual(payload.source_type, "internal")
        self.assertEqual(payload.source_label, "Internal Simulated Paper")
        self.assertTrue(payload.broker_connected)

    def test_portfolio_snapshot_keeps_clean_broker_when_internal_has_only_history(self):
        canonical_snapshot = PortfolioSnapshot(
            generated_at=datetime.now(UTC),
            positions=[],
            sources=[],
            total_market_value=0.0,
            total_unrealized_pnl=0.0,
        )
        internal_portfolio = {
            "items": [],
            "summary": {
                "open_positions": 0,
                "invested_cost": 0.0,
                "cash_balance": 100000.0,
                "total_equity": 100010.0,
                "portfolio_value": 100010.0,
                "total_market_value": 0.0,
                "total_unrealized_pnl": 0.0,
                "total_realized_pnl": 10.0,
                "total_trades": 2,
                "starting_cash": 100000.0,
            },
        }
        broker_summary = {
            "connected": True,
            "paper": True,
            "provider": "alpaca",
            "mode": "paper",
            "positions": [],
            "orders": [],
            "account": {"cash": 100000.0, "equity": 100000.0, "portfolio_value": 100000.0},
        }
        with patch("backend.app.application.portfolio.service.get_internal_portfolio", return_value=internal_portfolio), patch(
            "backend.app.application.portfolio.service.get_broker_summary", return_value=broker_summary
        ), patch("backend.app.application.portfolio.service.list_paper_orders", return_value={"items": []}), patch(
            "backend.app.application.portfolio.service.get_trade_history",
            return_value={"items": [{"symbol": "AAPL", "side": "BUY", "quantity": 1, "price": 180.0}]},
        ), patch("backend.app.application.portfolio.service.load_symbol_profiles", return_value={}), patch(
            "backend.app.application.portfolio.service.build_canonical_portfolio_snapshot",
            return_value=canonical_snapshot,
        ), patch(
            "backend.app.application.execution.service.sync_internal_positions_from_broker",
        ) as sync_mock:
            payload = build_portfolio_snapshot_payload()

        self.assertEqual(payload.active_source, "broker_paper")
        self.assertEqual(payload.source_type, "broker")
        self.assertEqual(payload.source_label, "Broker Paper")
        self.assertTrue(payload.broker_connected)
        sync_mock.assert_not_called()

    def test_portfolio_snapshot_resyncs_internal_positions_when_clean_broker_replaces_old_account(self):
        canonical_snapshot = PortfolioSnapshot(
            generated_at=datetime.now(UTC),
            positions=[],
            sources=[],
            total_market_value=0.0,
            total_unrealized_pnl=0.0,
        )
        stale_internal_portfolio = {
            "items": [
                {
                    "symbol": "AAPL",
                    "side": "LONG",
                    "quantity": 2,
                    "avg_entry_price": 180.0,
                    "current_price": 181.5,
                    "market_value": 363.0,
                    "unrealized_pnl": 3.0,
                    "realized_pnl": 0.0,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ],
            "summary": {
                "open_positions": 1,
                "invested_cost": 360.0,
                "cash_balance": 99640.0,
                "total_equity": 100003.0,
                "portfolio_value": 100003.0,
                "total_market_value": 363.0,
                "total_unrealized_pnl": 3.0,
                "total_realized_pnl": 0.0,
                "total_trades": 1,
                "starting_cash": 100000.0,
            },
        }
        synced_internal_portfolio = {
            "items": [],
            "summary": {
                "open_positions": 0,
                "invested_cost": 0.0,
                "cash_balance": 100000.0,
                "total_equity": 100000.0,
                "portfolio_value": 100000.0,
                "total_market_value": 0.0,
                "total_unrealized_pnl": 0.0,
                "total_realized_pnl": 0.0,
                "total_trades": 1,
                "starting_cash": 100000.0,
            },
        }
        broker_summary = {
            "connected": True,
            "paper": True,
            "provider": "alpaca",
            "mode": "paper",
            "positions": [],
            "orders": [],
            "account": {"cash": 100000.0, "equity": 100000.0, "portfolio_value": 100000.0},
        }
        with patch(
            "backend.app.application.portfolio.service.get_internal_portfolio",
            side_effect=[stale_internal_portfolio, synced_internal_portfolio],
        ), patch(
            "backend.app.application.portfolio.service.get_broker_summary", return_value=broker_summary
        ), patch("backend.app.application.portfolio.service.list_paper_orders", return_value={"items": []}), patch(
            "backend.app.application.portfolio.service.get_trade_history",
            return_value={"items": [{"symbol": "AAPL", "side": "BUY", "quantity": 2, "price": 180.0}]},
        ), patch("backend.app.application.portfolio.service.load_symbol_profiles", return_value={}), patch(
            "backend.app.application.portfolio.service.build_canonical_portfolio_snapshot",
            return_value=canonical_snapshot,
        ), patch(
            "backend.app.application.execution.service.sync_internal_positions_from_broker",
            return_value={"count": 0, "closed_symbols": ["AAPL"]},
        ) as sync_mock:
            payload = build_portfolio_snapshot_payload()

        self.assertEqual(payload.active_source, "broker_paper")
        self.assertEqual(payload.summary.open_positions, 0)
        self.assertTrue(payload.broker_connected)
        sync_mock.assert_called_once_with(strategy_mode="classic")

    def test_portfolio_snapshot_keeps_broker_when_broker_view_has_real_activity(self):
        canonical_snapshot = PortfolioSnapshot(
            generated_at=datetime.now(UTC),
            positions=[],
            sources=[],
            total_market_value=0.0,
            total_unrealized_pnl=0.0,
        )
        internal_portfolio = {
            "items": [
                {
                    "symbol": "MSFT",
                    "side": "LONG",
                    "quantity": 1,
                    "avg_entry_price": 400.0,
                    "current_price": 401.0,
                    "market_value": 401.0,
                    "unrealized_pnl": 1.0,
                    "realized_pnl": 0.0,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ],
            "summary": {
                "open_positions": 1,
                "invested_cost": 400.0,
                "cash_balance": 99600.0,
                "total_equity": 100001.0,
                "portfolio_value": 100001.0,
                "total_market_value": 401.0,
                "total_unrealized_pnl": 1.0,
                "total_realized_pnl": 0.0,
                "total_trades": 1,
                "starting_cash": 100000.0,
            },
        }
        broker_summary = {
            "connected": True,
            "paper": True,
            "provider": "alpaca",
            "mode": "paper",
            "positions": [
                {
                    "symbol": "NVDA",
                    "side": "buy",
                    "qty": 3,
                    "avg_entry_price": 900.0,
                    "current_price": 905.0,
                    "market_value": 2715.0,
                    "cost_basis": 2700.0,
                    "unrealized_pnl": 15.0,
                }
            ],
            "orders": [],
            "account": {"cash": 97285.0, "equity": 100000.0, "portfolio_value": 100000.0},
        }
        with patch("backend.app.application.portfolio.service.get_internal_portfolio", return_value=internal_portfolio), patch(
            "backend.app.application.portfolio.service.get_broker_summary", return_value=broker_summary
        ), patch("backend.app.application.portfolio.service.list_paper_orders", return_value={"items": []}), patch(
            "backend.app.application.portfolio.service.get_trade_history", return_value={"items": []}
        ), patch("backend.app.application.portfolio.service.load_symbol_profiles", return_value={}), patch(
            "backend.app.application.portfolio.service.build_canonical_portfolio_snapshot",
            return_value=canonical_snapshot,
        ):
            payload = build_portfolio_snapshot_payload()

        self.assertEqual(payload.active_source, "broker_paper")
        self.assertEqual(payload.source_type, "broker")
        self.assertEqual(payload.source_label, "Broker Paper")
        self.assertTrue(payload.broker_connected)


if __name__ == "__main__":
    unittest.main()
