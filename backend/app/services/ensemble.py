from __future__ import annotations

from backend.app.config import (
    DECISION_DIRECTIONAL_MIN_CONFIDENCE,
    DECISION_ENSEMBLE_BUY_THRESHOLD,
    DECISION_ENSEMBLE_SELL_THRESHOLD,
    DECISION_HOLD_MAX_CONFIDENCE,
)


def _signal_to_score(signal):
    signal = str(signal or "HOLD").upper()
    if signal == "BUY":
        return 1.0
    if signal == "SELL":
        return -1.0
    return 0.0


def _safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _signal_vote(payload: dict | None) -> float:
    if not isinstance(payload, dict) or payload.get("error"):
        return 0.0
    explicit = _signal_to_score(payload.get("signal"))
    if explicit != 0.0:
        return explicit
    prob_buy = _safe_float(payload.get("prob_buy"), 0.0)
    prob_sell = _safe_float(payload.get("prob_sell"), 0.0)
    if abs(prob_buy - prob_sell) < 0.08:
        return 0.0
    return 1.0 if prob_buy > prob_sell else -1.0


def _agreement_ratio(votes: list[float]) -> tuple[float, int]:
    directional = [vote for vote in votes if vote != 0.0]
    if not directional:
        return 0.0, 0
    buy_votes = sum(1 for vote in directional if vote > 0)
    sell_votes = sum(1 for vote in directional if vote < 0)
    contradictions = min(buy_votes, sell_votes)
    ratio = abs(sum(directional)) / max(1, len(directional))
    return float(max(0.0, min(1.0, ratio))), int(contradictions)


def build_ensemble_output(classic_result, ml_result=None, dl_result=None):
    classic_signal = str(classic_result.get("enhanced_signal", classic_result.get("signal", "HOLD"))).upper()
    ranking_confidence = _safe_float(classic_result.get("confidence"), 50.0)
    classic_component = _signal_to_score(classic_signal) * (ranking_confidence / 100.0)

    ml_component = 0.0
    dl_component = 0.0
    reasoning = [f"classic={classic_signal} conf={ranking_confidence}"]

    if isinstance(ml_result, dict) and not ml_result.get("error"):
        ml_component = (_safe_float(ml_result.get("prob_buy"), 0.0) - _safe_float(ml_result.get("prob_sell"), 0.0)) * 0.95
        reasoning.append(f"ml={ml_result.get('signal', 'HOLD')} conf={ml_result.get('confidence', 0.0)}")

    if isinstance(dl_result, dict) and not dl_result.get("error"):
        dl_component = (_safe_float(dl_result.get("prob_buy"), 0.0) - _safe_float(dl_result.get("prob_sell"), 0.0)) * 1.0
        reasoning.append(f"dl={dl_result.get('signal', 'HOLD')} conf={dl_result.get('confidence', 0.0)}")

    mtf_score = _safe_float(classic_result.get("mtf_score"), 0.0)
    regime_component = 0.12 if mtf_score > 0 else -0.12 if mtf_score < 0 else 0.0
    ensemble_score = classic_component + ml_component + dl_component + regime_component

    if ensemble_score > DECISION_ENSEMBLE_BUY_THRESHOLD:
        signal = "BUY"
    elif ensemble_score < DECISION_ENSEMBLE_SELL_THRESHOLD:
        signal = "SELL"
    else:
        signal = "HOLD"

    votes = [_signal_to_score(classic_signal), _signal_vote(ml_result), _signal_vote(dl_result)]
    agreement_ratio, contradiction_count = _agreement_ratio(votes)
    ml_certainty = 0.0
    dl_certainty = 0.0
    if isinstance(ml_result, dict) and not ml_result.get("error"):
        ml_certainty = abs(_safe_float(ml_result.get("prob_buy"), 0.0) - _safe_float(ml_result.get("prob_sell"), 0.0))
    if isinstance(dl_result, dict) and not dl_result.get("error"):
        dl_certainty = abs(_safe_float(dl_result.get("prob_buy"), 0.0) - _safe_float(dl_result.get("prob_sell"), 0.0))
    confidence_raw = (
        abs(ensemble_score) * 34.0
        + ranking_confidence * 0.26
        + agreement_ratio * 22.0
        + ml_certainty * 18.0
        + dl_certainty * 12.0
        - contradiction_count * 12.0
    )
    if signal == "HOLD":
        confidence_raw = min(confidence_raw, DECISION_HOLD_MAX_CONFIDENCE)
    confidence = min(99, max(0, int(round(confidence_raw))))

    if signal in {"BUY", "SELL"}:
        if confidence < DECISION_DIRECTIONAL_MIN_CONFIDENCE or agreement_ratio < 0.25:
            signal = "HOLD"
            confidence = min(int(DECISION_HOLD_MAX_CONFIDENCE), confidence)

    reasoning.append(f"agreement={agreement_ratio:.2f}")
    if contradiction_count > 0:
        reasoning.append(f"contradictions={contradiction_count}")

    return {
        "signal": signal,
        "ensemble_score": round(float(ensemble_score), 4),
        "confidence": confidence,
        "agreement_ratio": round(float(agreement_ratio), 4),
        "contradiction_count": int(contradiction_count),
        "reasoning": " | ".join(reasoning),
        "components": {
            "classic_component": round(classic_component, 4),
            "ml_component": round(ml_component, 4),
            "dl_component": round(dl_component, 4),
            "regime_component": round(regime_component, 4),
        },
    }
