from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from backend.app.application.broker.service import liquidate_broker_positions
from backend.app.core.date_defaults import indicator_warmup_start_date_iso
from backend.app.services.explainability import build_signal_explanation
from core.analysis_service import analyze_symbol
from news_engine import fetch_news


class DummyResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def test_analyze_symbol_uses_indicator_warmup_and_trims_visible_window():
    payload = {
        "chart_data": {
            "dates": ["2026-03-30", "2026-04-01", "2026-04-05", "2026-04-12"],
            "close": [10, 11, 12, 13],
            "ma20": [9, 10, 11, 12],
        },
        "table_data": [
            {"date": "2026-03-30", "close": 10},
            {"date": "2026-04-01", "close": 11},
            {"date": "2026-04-05", "close": 12},
            {"date": "2026-04-12", "close": 13},
        ],
        "confidence": 70,
        "signal": "BUY",
        "enhanced_signal": "BUY",
        "news_items": [],
    }

    with patch("core.analysis_service.engine_run_analysis", return_value=payload) as mocked_engine, patch(
        "core.analysis_service.enhance_signal",
        side_effect=lambda result: result,
    ):
        result = analyze_symbol("AAPL", "2026-04-01", "2026-04-10")

    _, kwargs = mocked_engine.call_args
    assert kwargs["start_date"] == indicator_warmup_start_date_iso("2026-04-01")
    assert kwargs["end_date"] == "2026-04-10"
    assert result["chart_data"]["dates"] == ["2026-04-01", "2026-04-05"]
    assert [row["date"] for row in result["table_data"]] == ["2026-04-01", "2026-04-05"]
    assert result["start_date"] == "2026-04-01"
    assert result["end_date"] == "2026-04-10"


def test_liquidate_broker_positions_refuses_non_paper_account():
    live_summary = {
        "provider": "alpaca",
        "mode": "live",
        "paper": False,
        "live_execution_enabled": True,
        "positions": [{"symbol": "AAPL"}],
        "totals": {"open_orders": 1},
    }
    with patch("backend.app.application.broker.service.get_broker_summary", return_value=live_summary), patch(
        "backend.app.application.broker.service._liquidate_broker_positions"
    ) as mocked_liquidate:
        result = liquidate_broker_positions(cancel_open_orders=True)

    assert result["ok"] is False
    assert "non-paper" in result["error"].lower()
    mocked_liquidate.assert_not_called()


def test_fetch_news_deduplicates_exact_and_semantic_updates():
    rss = """<?xml version='1.0' encoding='UTF-8'?>
    <rss><channel>
      <item>
        <title>Apple beats earnings and raises guidance</title>
        <link>https://example.com/1</link>
        <pubDate>Thu, 16 Apr 2026 09:00:00 GMT</pubDate>
        <source>Unknown</source>
      </item>
      <item>
        <title>Apple beats earnings and raises guidance</title>
        <link>https://example.com/1</link>
        <pubDate>Thu, 16 Apr 2026 09:00:00 GMT</pubDate>
        <source>Unknown</source>
      </item>
      <item>
        <title>Apple beats earnings, raises guidance for next quarter</title>
        <link>https://example.com/2</link>
        <pubDate>Thu, 16 Apr 2026 09:05:00 GMT</pubDate>
        <source>Reuters</source>
      </item>
      <item>
        <title>Apple launches new enterprise AI product</title>
        <link>https://example.com/3</link>
        <pubDate>Thu, 16 Apr 2026 10:00:00 GMT</pubDate>
        <source>CNBC</source>
      </item>
    </channel></rss>""".encode()

    with patch("news_engine.requests.get", return_value=DummyResponse(rss)):
        payload = fetch_news("AAPL", limit=10)

    assert payload["articles_count"] == 2
    first = payload["news_items"][0]
    assert first["source"] == "Reuters"
    assert first["event_relation"] == "event_update"
    assert first["event_type"] == "earnings"
    assert first["sentiment"] == "POSITIVE"


def test_signal_explanation_is_grounded_in_news_event_facts():
    explanation = build_signal_explanation(
        {
            "enhanced_signal": "BUY",
            "confidence": 72,
            "technical_score": 4,
            "mtf_score": 2,
            "rs_score": 1,
            "trend_quality_score": 1,
            "ml_output": {"prob_buy": 0.62, "prob_sell": 0.18},
            "news_items": [
                {
                    "sentiment": "POSITIVE",
                    "event_type": "earnings",
                }
            ],
        }
    )

    assert explanation["signal"] == "BUY"
    assert any("earnings" in item.lower() for item in explanation["supporting_factors"])
    assert "technical alignment" in explanation["summary"].lower()
