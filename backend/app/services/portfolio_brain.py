"""Compatibility facade for portfolio-brain modules.

Canonical implementation now lives under `backend.app.services.portfolio_brain.*`.
"""

from backend.app.services.portfolio_brain.decision_policy import resolve_action
from backend.app.services.portfolio_brain.explanation_payload import build_chart_plan
from backend.app.services.portfolio_brain.opportunity_scoring import compute_opportunity_score
from backend.app.services.portfolio_brain.queue_prioritization import prioritize_opportunities
from backend.app.services.portfolio_brain.service import build_portfolio_brain_payload
from backend.app.services.portfolio_brain.sleeve_allocation import allocate_sleeves

__all__ = [
    "allocate_sleeves",
    "build_chart_plan",
    "build_portfolio_brain_payload",
    "compute_opportunity_score",
    "prioritize_opportunities",
    "resolve_action",
]
