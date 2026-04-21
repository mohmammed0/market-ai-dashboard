"""Sleeve allocation helper for ranked opportunities."""

from __future__ import annotations


def allocate_sleeves(opportunities: list[dict], max_items: int = 5) -> list[dict]:
    ranked = sorted(
        list(opportunities or []),
        key=lambda row: (
            -float(row.get("opportunity_score") or 0.0),
            -float(row.get("confidence") or 0.0),
        ),
    )[: max(1, int(max_items or 5))]
    if not ranked:
        return []

    total = sum(max(float(row.get("opportunity_score") or 0.0), 0.0) for row in ranked)
    if total <= 0:
        equal = round(1.0 / len(ranked), 6)
        return [{**row, "target_weight": equal} for row in ranked]

    allocations = []
    for row in ranked:
        raw = max(float(row.get("opportunity_score") or 0.0), 0.0) / total
        allocations.append({**row, "target_weight": round(raw, 6)})
    return allocations
