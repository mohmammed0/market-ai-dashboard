from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from backend.app.application.broker.service import liquidate_broker_positions
from backend.app.config import DEFAULT_SAMPLE_SYMBOLS, DECISION_OPPORTUNITY_MIN_CONFIDENCE
from backend.app.core.date_defaults import indicator_warmup_start_date_iso
from backend.app.services.confidence_calibration import apply_confidence_calibration_to_analysis, calibrate_confidence
from backend.app.services.dashboard_summary_helpers import _derive_action, _is_actionable_opportunity
from backend.app.services.explainability import build_signal_explanation
from backend.app.services.market_universe import resolve_universe_preset
from backend.app.services.runtime_settings import get_auto_trading_config
from core.analysis_service import analyze_symbol
from core.legacy_adapters.news import fetch_news


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


def test_signal_explanation_prefers_ensemble_confidence_when_available():
    explanation = build_signal_explanation(
        {
            "enhanced_signal": "HOLD",
            "confidence": 62,
            "technical_score": 0,
            "ensemble_output": {"signal": "HOLD", "confidence": 34, "reasoning": "agreement=0.33"},
        }
    )

    assert explanation["confidence"] == 34
    assert "34%" in explanation["summary"]
    assert "62%" not in explanation["summary"]


def test_decision_action_mapping_prefers_useful_actions():
    assert _derive_action("BUY", 83, {"technical_score": 2, "mtf_score": 1, "rs_score": 1}) == "BUY"
    assert _derive_action("BUY", 68, {"technical_score": 1, "mtf_score": 0, "rs_score": 0}) == "ADD"
    assert _derive_action("SELL", 82, {"technical_score": -2, "news_items": [{"sentiment": "NEGATIVE"}]}) == "EXIT"
    assert _derive_action(
        "HOLD",
        61,
        {
            "technical_score": -2,
            "news_items": [{"sentiment": "NEGATIVE"}],
            "ml_output": {"prob_buy": 0.21, "prob_sell": 0.58},
        },
    ) == "TRIM"


def test_actionable_filter_rejects_weak_watchs():
    assert _is_actionable_opportunity("WATCH", 50, 0.2, None) is False
    assert _is_actionable_opportunity("WATCH", 50, 0.2, "earnings") is False
    assert _is_actionable_opportunity("WATCH", 57, 0.9, "earnings") is True
    assert _is_actionable_opportunity("ADD", DECISION_OPPORTUNITY_MIN_CONFIDENCE, 0.2, None) is True
    assert _is_actionable_opportunity("ADD", DECISION_OPPORTUNITY_MIN_CONFIDENCE - 1, 0.2, None) is False


def test_confidence_calibration_reduces_overconfident_top_band():
    profile = {
        "enabled": True,
        "status": "ready",
        "samples_count": 120,
        "bands": {
            "85-100": {"samples": 80, "win_rate_pct": 46.0},
        },
        "actions": {
            "BUY": {"samples": 60, "win_rate_pct": 42.0},
            "ADD": {"samples": 20, "win_rate_pct": 48.0},
        },
    }
    calibrated = calibrate_confidence(95, "BUY", profile)
    assert calibrated < 80
    assert calibrated >= 0


def test_confidence_calibration_keeps_directional_strength_when_empirical_is_good():
    profile = {
        "enabled": True,
        "status": "ready",
        "samples_count": 160,
        "bands": {
            "70-85": {"samples": 70, "win_rate_pct": 74.0},
            "85-100": {"samples": 20, "win_rate_pct": 76.0},
        },
        "actions": {
            "BUY": {"samples": 90, "win_rate_pct": 75.0},
        },
    }
    calibrated = calibrate_confidence(82, "BUY", profile)
    assert calibrated >= 62
    assert calibrated <= 90


def test_apply_confidence_calibration_updates_analysis_payload():
    profile = {
        "enabled": True,
        "status": "ready",
        "generated_at": "2026-04-17T00:00:00Z",
        "samples_count": 120,
        "bands": {
            "85-100": {"samples": 80, "win_rate_pct": 46.0},
        },
        "actions": {
            "BUY": {"samples": 60, "win_rate_pct": 42.0},
        },
    }
    analysis = {
        "signal": "BUY",
        "enhanced_signal": "BUY",
        "confidence": 92,
        "ensemble_output": {"signal": "BUY", "confidence": 95},
    }
    output = apply_confidence_calibration_to_analysis(analysis, profile)
    assert output["confidence"] < 92
    assert output["ensemble_output"]["confidence"] < 95
    assert output["confidence_calibration"]["applied"] is True


def test_resolve_universe_preset_supports_focused_sample(monkeypatch):
    monkeypatch.setattr("backend.app.services.market_universe.ensure_market_universe", lambda: {"ok": True})
    payload = resolve_universe_preset("FOCUSED_SAMPLE", limit=5)

    assert payload["preset"] == "FOCUSED_SAMPLE"
    assert payload["returned_count"] == 5
    assert payload["symbols"] == DEFAULT_SAMPLE_SYMBOLS[:5]


def test_auto_trading_config_uses_config_default_preset(monkeypatch):
    monkeypatch.setattr("backend.app.services.runtime_settings._resolve_setting", lambda key, records=None: {
        "auto_trading.enabled": (True, "default"),
        "auto_trading.cycle_minutes": (5, "default"),
        "auto_trading.universe_preset": ("", "default"),
        "broker.order_submission_enabled": (True, "default"),
    }[key])
    monkeypatch.setattr(
        "backend.app.services.runtime_settings.get_alpaca_runtime_config",
        lambda: {"trading_mode": "cash", "margin_enabled": False, "enabled": True, "configured": True, "paper": True},
    )
    monkeypatch.setattr("backend.app.services.runtime_settings.AUTO_TRADING_UNIVERSE_PRESET", "FOCUSED_SAMPLE")

    payload = get_auto_trading_config()

    assert payload["universe_preset"] == "FOCUSED_SAMPLE"
