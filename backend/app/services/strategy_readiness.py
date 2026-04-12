"""Strategy Readiness Classification.

Deterministic rules that classify strategy evaluation results into
readiness states based on existing strategy-lab outputs.

States
------
exploratory     Insufficient data or weak initial results.
candidate       Reasonable metrics — suitable for deeper review.
review_ready    Strong walk-forward stability, no overfit flag, solid robust score.
rejected        Overfit, extremely decayed OOS, or negative robust score.

All thresholds are explicit and inspectable.  No ML or fuzzy logic
is used — an operator can reason about every classification by reading
the ``reasons`` list in the return dict.
"""

from __future__ import annotations

from typing import Any

READINESS_STATES = {
    "exploratory": "Early-stage evaluation — insufficient validation data for promotion",
    "candidate": "Reasonable results — suitable for further review",
    "review_ready": "Strong results with validated walk-forward stability — ready for review",
    "rejected": "Weak, overfit, or unstable results — not suitable for promotion",
}

# ── Thresholds (explicit, inspectable) ────────────────────────────────
REJECT_OVERFIT_SCORE_BELOW = 40        # overfit_score < 40 → rejected
REJECT_OOS_DECAY_ABOVE = 60            # |oos_decay_pct| > 60 → rejected
REJECT_ROBUST_SCORE_BELOW = -5         # best robust_score < -5 → rejected

REVIEW_OVERFIT_SCORE_ABOVE = 60        # overfit_score ≥ 60 → eligible for review_ready
REVIEW_OOS_DECAY_BELOW = 30            # |oos_decay_pct| ≤ 30
REVIEW_ROBUST_SCORE_ABOVE = 5          # robust_score ≥ 5
REVIEW_MIN_WALK_FORWARD_WINDOWS = 2    # at least 2 walk-forward windows

CANDIDATE_ROBUST_SCORE_ABOVE = 0       # robust_score ≥ 0
CANDIDATE_OVERFIT_SCORE_ABOVE = 40     # overfit_score ≥ 40


def classify_strategy_run(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Classify a single strategy evaluation into a readiness state.

    Parameters
    ----------
    evaluation : dict
        Must contain ``overfitting``, ``leaderboard``, and ``walk_forward``
        keys — matching the shape returned by ``run_strategy_evaluation()``.

    Returns
    -------
    dict with ``state``, ``reasons``, ``description``, and ``thresholds_used``.
    """
    overfitting = evaluation.get("overfitting") or {}
    leaderboard = evaluation.get("leaderboard") or []
    walk_forward = evaluation.get("walk_forward") or []

    overfit_flag = overfitting.get("overfit_flag", False)
    overfit_score = float(overfitting.get("overfit_score", 0))
    oos_decay_pct = abs(float(overfitting.get("oos_decay_pct", 100)))
    best_robust_score = float(leaderboard[0].get("robust_score", 0)) if leaderboard else 0
    wf_count = len(walk_forward)

    thresholds = {
        "reject_overfit_score_below": REJECT_OVERFIT_SCORE_BELOW,
        "reject_oos_decay_above": REJECT_OOS_DECAY_ABOVE,
        "reject_robust_score_below": REJECT_ROBUST_SCORE_BELOW,
        "review_overfit_score_above": REVIEW_OVERFIT_SCORE_ABOVE,
        "review_oos_decay_below": REVIEW_OOS_DECAY_BELOW,
        "review_robust_score_above": REVIEW_ROBUST_SCORE_ABOVE,
        "review_min_wf_windows": REVIEW_MIN_WALK_FORWARD_WINDOWS,
    }

    # ── Rejection ─────────────────────────────────────────────────────
    rejection_reasons: list[str] = []
    if overfit_flag and overfit_score < REJECT_OVERFIT_SCORE_BELOW:
        rejection_reasons.append(
            f"Overfit flag active with low score ({overfit_score:.0f} < {REJECT_OVERFIT_SCORE_BELOW})"
        )
    if oos_decay_pct > REJECT_OOS_DECAY_ABOVE:
        rejection_reasons.append(
            f"Extreme OOS decay ({oos_decay_pct:.1f}% > {REJECT_OOS_DECAY_ABOVE}%)"
        )
    if best_robust_score < REJECT_ROBUST_SCORE_BELOW:
        rejection_reasons.append(
            f"Negative robust score ({best_robust_score:.1f} < {REJECT_ROBUST_SCORE_BELOW})"
        )

    if rejection_reasons:
        return {
            "state": "rejected",
            "reasons": rejection_reasons,
            "description": READINESS_STATES["rejected"],
            "metrics_snapshot": _metrics_snapshot(overfit_score, oos_decay_pct, best_robust_score, wf_count),
            "thresholds_used": thresholds,
        }

    # ── Review-ready ──────────────────────────────────────────────────
    review_ready = (
        not overfit_flag
        and overfit_score >= REVIEW_OVERFIT_SCORE_ABOVE
        and oos_decay_pct <= REVIEW_OOS_DECAY_BELOW
        and best_robust_score >= REVIEW_ROBUST_SCORE_ABOVE
        and wf_count >= REVIEW_MIN_WALK_FORWARD_WINDOWS
    )
    if review_ready:
        return {
            "state": "review_ready",
            "reasons": [
                f"Overfit score healthy ({overfit_score:.0f} >= {REVIEW_OVERFIT_SCORE_ABOVE})",
                f"OOS decay acceptable ({oos_decay_pct:.1f}% <= {REVIEW_OOS_DECAY_BELOW}%)",
                f"Robust score strong ({best_robust_score:.1f} >= {REVIEW_ROBUST_SCORE_ABOVE})",
                f"Walk-forward validated ({wf_count} windows >= {REVIEW_MIN_WALK_FORWARD_WINDOWS})",
            ],
            "description": READINESS_STATES["review_ready"],
            "metrics_snapshot": _metrics_snapshot(overfit_score, oos_decay_pct, best_robust_score, wf_count),
            "thresholds_used": thresholds,
        }

    # ── Candidate ─────────────────────────────────────────────────────
    if best_robust_score >= CANDIDATE_ROBUST_SCORE_ABOVE and overfit_score >= CANDIDATE_OVERFIT_SCORE_ABOVE:
        return {
            "state": "candidate",
            "reasons": [
                f"Positive robust score ({best_robust_score:.1f} >= {CANDIDATE_ROBUST_SCORE_ABOVE})",
                f"Acceptable overfit score ({overfit_score:.0f} >= {CANDIDATE_OVERFIT_SCORE_ABOVE})",
            ],
            "description": READINESS_STATES["candidate"],
            "metrics_snapshot": _metrics_snapshot(overfit_score, oos_decay_pct, best_robust_score, wf_count),
            "thresholds_used": thresholds,
        }

    # ── Exploratory (default) ─────────────────────────────────────────
    return {
        "state": "exploratory",
        "reasons": ["Insufficient validation metrics for promotion"],
        "description": READINESS_STATES["exploratory"],
        "metrics_snapshot": _metrics_snapshot(overfit_score, oos_decay_pct, best_robust_score, wf_count),
        "thresholds_used": thresholds,
    }


def _metrics_snapshot(overfit_score: float, oos_decay_pct: float,
                      robust_score: float, wf_count: int) -> dict:
    return {
        "overfit_score": round(overfit_score, 1),
        "oos_decay_pct": round(oos_decay_pct, 1),
        "best_robust_score": round(robust_score, 2),
        "walk_forward_windows": wf_count,
    }


def get_readiness_summary(limit: int = 20) -> dict:
    """Classify recent strategy evaluations and return a readiness summary.

    Returns
    -------
    dict with ``items`` (classified evaluations), ``summary`` (state counts),
    and ``total``.
    """
    from backend.app.services.strategy_lab import list_strategy_evaluations  # noqa: PLC0415

    evaluations = list_strategy_evaluations(limit=limit)

    items: list[dict] = []
    state_counts = {"exploratory": 0, "candidate": 0, "review_ready": 0, "rejected": 0}

    for eval_item in evaluations.get("items", []):
        metrics = eval_item.get("metrics") or {}
        leaderboard = eval_item.get("leaderboard") or []

        classification = classify_strategy_run({
            "overfitting": metrics.get("overfitting", {}),
            "leaderboard": leaderboard,
            "walk_forward": metrics.get("walk_forward", []),
        })

        items.append({
            "run_id": eval_item.get("run_id"),
            "instrument": eval_item.get("instrument"),
            "status": eval_item.get("status"),
            "completed_at": eval_item.get("completed_at"),
            "best_strategy": metrics.get("best_strategy"),
            "config_hash": (metrics.get("config_hash")
                            or (eval_item.get("metrics") or {}).get("config_hash")),
            "readiness": classification,
        })
        state_counts[classification["state"]] = state_counts.get(classification["state"], 0) + 1

    return {
        "items": items,
        "summary": state_counts,
        "total": len(items),
        "thresholds": {
            "rejection": {
                "overfit_score_below": REJECT_OVERFIT_SCORE_BELOW,
                "oos_decay_above": REJECT_OOS_DECAY_ABOVE,
                "robust_score_below": REJECT_ROBUST_SCORE_BELOW,
            },
            "review_ready": {
                "overfit_score_above": REVIEW_OVERFIT_SCORE_ABOVE,
                "oos_decay_below": REVIEW_OOS_DECAY_BELOW,
                "robust_score_above": REVIEW_ROBUST_SCORE_ABOVE,
                "min_walk_forward_windows": REVIEW_MIN_WALK_FORWARD_WINDOWS,
            },
            "candidate": {
                "robust_score_above": CANDIDATE_ROBUST_SCORE_ABOVE,
                "overfit_score_above": CANDIDATE_OVERFIT_SCORE_ABOVE,
            },
        },
    }
