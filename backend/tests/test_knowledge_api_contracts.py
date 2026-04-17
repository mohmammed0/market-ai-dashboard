from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.db.session import engine
from backend.app.models.knowledge import KnowledgeDocument


class KnowledgeApiContractsTests(unittest.TestCase):
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

    def test_knowledge_ingest_route_contract(self):
        fake_result = {
            "ingested": 1,
            "items": [{"document_id": "doc-1", "source_type": "manual_note", "symbol": "AAPL"}],
        }
        with patch("backend.app.api.routes.knowledge.ingest_knowledge_documents", return_value=fake_result) as ingest_mock:
            response = self.client.post(
                "/api/knowledge/ingest",
                json={
                    "items": [
                        {
                            "source_type": "manual_note",
                            "symbol": "AAPL",
                            "title": "Earnings memo",
                            "summary": "Strong guidance",
                            "content": "Revenue and margin both exceeded estimates.",
                            "tags": ["earnings", "ai"],
                            "metadata": {"importance_boost": 0.6},
                        }
                    ]
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["ingested"], 1)
        self.assertEqual(payload["items"][0]["document_id"], "doc-1")
        ingest_mock.assert_called_once()
        args, kwargs = ingest_mock.call_args
        self.assertEqual(kwargs["default_source_type"], "manual_note")
        self.assertEqual(args[0][0]["symbol"], "AAPL")

    def test_knowledge_search_route_parses_tags(self):
        fake_result = {
            "items": [
                {
                    "document_id": "doc-2",
                    "title": "AAPL setup",
                    "source_type": "ai_research_report",
                    "hybrid_score": 2.4,
                }
            ],
            "count": 1,
            "retrieval": {"mode": "lexical", "vector_ready": False, "vector_provider": "disabled"},
        }
        with patch("backend.app.api.routes.knowledge.search_knowledge_documents", return_value=fake_result) as search_mock:
            response = self.client.get(
                "/api/knowledge/search?q=earnings&symbol=AAPL&source_type=ai_research_report&tags=ai,earnings&limit=5&offset=0&use_vector=true"
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["document_id"], "doc-2")
        _, kwargs = search_mock.call_args
        self.assertEqual(kwargs["query_text"], "earnings")
        self.assertEqual(kwargs["symbol"], "AAPL")
        self.assertEqual(kwargs["source_type"], "ai_research_report")
        self.assertEqual(kwargs["tags"], ["ai", "earnings"])
        self.assertEqual(kwargs["limit"], 5)
        self.assertTrue(kwargs["use_vector"])

    def test_knowledge_document_404_when_missing(self):
        with patch("backend.app.api.routes.knowledge.get_knowledge_document", return_value=None):
            response = self.client.get("/api/knowledge/documents/missing-document")

        self.assertEqual(response.status_code, 404, response.text)
        self.assertIn("Knowledge document not found", response.text)

    def test_ai_research_route_contract(self):
        fake_result = {
            "research_id": "research-abc123",
            "symbol": "AAPL",
            "action": "buy",
            "signal": "BUY",
            "confidence": 78.5,
            "risk_level": "moderate",
            "summary": "Momentum and news alignment remain constructive.",
            "evidence": [{"type": "knowledge", "document_id": "doc-1"}],
            "llm": {"provider": "deterministic", "used": False},
        }
        with patch("backend.app.api.routes.ai_research.build_symbol_research", return_value=fake_result) as research_mock:
            response = self.client.post(
                "/api/ai/research",
                json={
                    "symbol": "AAPL",
                    "question": "Should we add here?",
                    "knowledge_limit": 6,
                    "include_news": True,
                    "use_vector": False,
                    "context_document_ids": ["doc-1"],
                    "persist": False,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["research_id"], "research-abc123")
        self.assertEqual(payload["symbol"], "AAPL")
        self.assertEqual(payload["action"], "buy")
        _, kwargs = research_mock.call_args
        self.assertEqual(kwargs["symbol"], "AAPL")
        self.assertEqual(kwargs["knowledge_limit"], 6)
        self.assertEqual(kwargs["context_document_ids"], ["doc-1"])
        self.assertFalse(kwargs["persist"])

    def test_ai_contextual_analyze_alias_uses_same_service(self):
        fake_result = {"research_id": "research-x", "symbol": "MSFT", "action": "watch"}
        with patch("backend.app.api.routes.ai_research.build_symbol_research", return_value=fake_result) as research_mock:
            response = self.client.post(
                "/api/ai/contextual-analyze",
                json={"symbol": "MSFT", "question": "Context check", "persist": False},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["research_id"], "research-x")
        research_mock.assert_called_once()

    def test_ai_market_brief_contract(self):
        fake_result = {
            "brief_id": "brief-1",
            "symbols": ["AAPL", "MSFT"],
            "summary": "Brief generated for two symbols.",
            "research_items": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
        }
        with patch("backend.app.api.routes.ai_research.build_market_brief", return_value=fake_result) as brief_mock:
            response = self.client.post(
                "/api/ai/market-brief",
                json={
                    "question": "What matters this session?",
                    "symbols": ["AAPL", "MSFT"],
                    "limit": 4,
                    "use_vector": False,
                    "persist": True,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["brief_id"], "brief-1")
        self.assertEqual(len(payload["research_items"]), 2)
        _, kwargs = brief_mock.call_args
        self.assertEqual(kwargs["symbols"], ["AAPL", "MSFT"])
        self.assertEqual(kwargs["limit"], 4)
        self.assertTrue(kwargs["persist"])

    def test_smoke_end_to_end_knowledge_and_ai_research(self):
        KnowledgeDocument.__table__.create(bind=engine, checkfirst=True)

        ingest_response = self.client.post(
            "/api/knowledge/ingest",
            json={
                "items": [
                    {
                        "source_type": "manual_note",
                        "symbol": "AAPL",
                        "title": "AAPL earnings signal note",
                        "summary": "Earnings momentum remains constructive.",
                        "content": "Multiple factors support a constructive short-horizon setup.",
                        "tags": ["earnings", "momentum"],
                        "metadata": {"importance_boost": 0.9},
                        "provenance": {"source": "smoke_test"},
                    }
                ]
            },
        )
        self.assertEqual(ingest_response.status_code, 200, ingest_response.text)
        ingest_payload = ingest_response.json()
        self.assertGreaterEqual(int(ingest_payload.get("inserted") or 0), 1)
        document_id = (ingest_payload.get("items") or [{}])[0].get("document_id")
        self.assertTrue(document_id)

        search_response = self.client.get("/api/knowledge/search?q=earnings&symbol=AAPL&tags=momentum")
        self.assertEqual(search_response.status_code, 200, search_response.text)
        search_payload = search_response.json()
        self.assertGreaterEqual(int(search_payload.get("count") or 0), 1)
        found = [item for item in search_payload.get("items", []) if item.get("document_id") == document_id]
        self.assertTrue(found)

        open_response = self.client.get(f"/api/knowledge/documents/{document_id}")
        self.assertEqual(open_response.status_code, 200, open_response.text)
        open_payload = open_response.json()
        self.assertEqual(open_payload.get("document_id"), document_id)
        self.assertEqual(open_payload.get("symbol"), "AAPL")

        fake_signal = {
            "symbol": "AAPL",
            "mode": "ensemble",
            "signal": "BUY",
            "confidence": 79.0,
            "price": 187.2,
            "reasoning": "cached signal for smoke validation",
        }
        fake_quote = {"items": [{"symbol": "AAPL", "price": 187.2, "change_pct": 1.12, "source": "smoke"}]}
        fake_news = [
            {
                "instrument": "AAPL",
                "title": "Analyst upgrade after earnings",
                "event_type": "analyst_upgrade",
                "sentiment": "POSITIVE",
                "impact_score": 0.8,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        fake_llm = {
            "summary": "Evidence supports a constructive near-term view.",
            "key_points": ["Trend and earnings follow-through are aligned."],
            "risk_notes": ["Protect with clear stop discipline."],
            "confidence_comment": "Confidence is supported by both market and news context.",
            "provider": "stub",
            "model": "stub-small",
        }
        with patch("backend.app.services.ai_research.get_cached_signal_view", return_value=fake_signal), patch(
            "backend.app.services.ai_research.warm_signal_cache_for_symbol",
            return_value=None,
        ), patch("backend.app.services.ai_research.fetch_quote_snapshots", return_value=fake_quote), patch(
            "backend.app.services.ai_research._fetch_recent_news",
            return_value=fake_news,
        ), patch("backend.app.services.ai_research._build_llm_summary", return_value=fake_llm):
            research_response = self.client.post(
                "/api/ai/research",
                json={
                    "symbol": "AAPL",
                    "question": "Give me a concise actionable read.",
                    "context_document_ids": [document_id],
                    "knowledge_limit": 6,
                    "persist": False,
                    "include_news": True,
                    "use_vector": False,
                },
            )

        self.assertEqual(research_response.status_code, 200, research_response.text)
        research_payload = research_response.json()
        self.assertEqual(research_payload.get("symbol"), "AAPL")
        self.assertIn(research_payload.get("action"), {"buy", "add", "watch"})
        self.assertTrue(research_payload.get("evidence"))
        evidence_doc_ids = [item.get("document_id") for item in research_payload.get("evidence", [])]
        self.assertIn(document_id, evidence_doc_ids)


class KnowledgeAuthGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.auth_enabled_patcher = patch("backend.app.main.AUTH_ENABLED", True)
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

    def test_knowledge_recent_requires_auth_when_enabled(self):
        response = self.client.get("/api/knowledge/recent")
        self.assertEqual(response.status_code, 401, response.text)
        self.assertIn("Authentication required", response.text)

    def test_ai_research_requires_auth_when_enabled(self):
        response = self.client.post(
            "/api/ai/research",
            json={"symbol": "AAPL", "question": "Auth guard check"},
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertIn("Authentication required", response.text)


if __name__ == "__main__":
    unittest.main()
