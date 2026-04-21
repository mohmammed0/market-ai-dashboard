from __future__ import annotations

from backend.app.services import portfolio_brain as portfolio_brain_facade
from backend.app.services.portfolio_brain.decision_policy import resolve_action
from backend.app.services.portfolio_brain.opportunity_scoring import compute_opportunity_score
from backend.app.services.portfolio_brain.queue_prioritization import prioritize_opportunities
from backend.app.services.portfolio_brain.service import build_portfolio_brain_payload


def test_portfolio_brain_facade_exports_service_builder():
    assert callable(portfolio_brain_facade.build_portfolio_brain_payload)


def test_portfolio_brain_policy_and_scoring():
    analysis = {
        "technical_score": 2.0,
        "ensemble_output": {"ensemble_score": 0.75},
        "ml_output": {"prob_buy": 0.62, "prob_sell": 0.21},
        "news_items": [{"sentiment": "POSITIVE", "impact_score": 0.9, "title": "Earnings beat"}],
        "confidence": 72.0,
        "action": "BUY",
        "signal": "BUY",
        "close": 100.0,
        "support": 97.5,
        "resistance": 105.0,
        "atr14": 2.2,
    }

    action = resolve_action("BUY", 72.0, analysis)
    assert action in {"BUY", "ADD", "WATCH"}

    score = compute_opportunity_score(analysis)
    assert score > 0

    payload = build_portfolio_brain_payload(
        symbol="AAPL",
        action=action,
        confidence=72.0,
        analysis=analysis,
    )
    assert payload["symbol"] == "AAPL"
    assert "opportunity_score" in payload
    assert "news_judgment" in payload


def test_queue_prioritization_prefers_higher_score():
    rows = [
        {"symbol": "B", "opportunity_score": 50, "confidence": 55},
        {"symbol": "A", "opportunity_score": 80, "confidence": 60},
        {"symbol": "C", "opportunity_score": 80, "confidence": 58},
    ]
    ranked = prioritize_opportunities(rows, limit=2)
    assert [row["symbol"] for row in ranked] == ["A", "C"]
