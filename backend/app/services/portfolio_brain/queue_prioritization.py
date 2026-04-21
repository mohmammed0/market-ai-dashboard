"""Queue prioritization for portfolio-brain opportunity lists."""

from __future__ import annotations


def prioritize_opportunities(opportunities: list[dict], limit: int = 5) -> list[dict]:
    bounded_limit = max(1, min(int(limit or 5), 25))
    ranked = sorted(
        list(opportunities or []),
        key=lambda row: (
            -float(row.get("opportunity_score") or 0.0),
            -float(row.get("confidence") or 0.0),
            str(row.get("symbol") or ""),
        ),
    )
    return ranked[:bounded_limit]
