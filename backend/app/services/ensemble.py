from __future__ import annotations


def _signal_to_score(signal):
    signal = str(signal or "HOLD").upper()
    if signal == "BUY":
        return 1.0
    if signal == "SELL":
        return -1.0
    return 0.0


def build_ensemble_output(classic_result, ml_result=None, dl_result=None):
    classic_signal = str(classic_result.get("enhanced_signal", classic_result.get("signal", "HOLD"))).upper()
    ranking_confidence = float(classic_result.get("confidence", 50) or 50)
    classic_component = _signal_to_score(classic_signal) * (ranking_confidence / 100.0)

    ml_component = 0.0
    dl_component = 0.0
    reasoning = [f"classic={classic_signal} conf={ranking_confidence}"]

    if isinstance(ml_result, dict) and not ml_result.get("error"):
        ml_component = (float(ml_result.get("prob_buy", 0.0)) - float(ml_result.get("prob_sell", 0.0))) * 1.1
        reasoning.append(f"ml={ml_result.get('signal', 'HOLD')} conf={ml_result.get('confidence', 0.0)}")

    if isinstance(dl_result, dict) and not dl_result.get("error"):
        dl_component = (float(dl_result.get("prob_buy", 0.0)) - float(dl_result.get("prob_sell", 0.0))) * 1.15
        reasoning.append(f"dl={dl_result.get('signal', 'HOLD')} conf={dl_result.get('confidence', 0.0)}")

    mtf_score = float(classic_result.get("mtf_score", 0) or 0)
    regime_component = 0.15 if mtf_score > 0 else -0.15 if mtf_score < 0 else 0.0
    ensemble_score = classic_component + ml_component + dl_component + regime_component

    if ensemble_score > 0.35:
        signal = "BUY"
    elif ensemble_score < -0.35:
        signal = "SELL"
    else:
        signal = "HOLD"

    confidence = min(99, max(0, int(round(abs(ensemble_score) * 45 + ranking_confidence * 0.35))))
    return {
        "signal": signal,
        "ensemble_score": round(float(ensemble_score), 4),
        "confidence": confidence,
        "reasoning": " | ".join(reasoning),
        "components": {
            "classic_component": round(classic_component, 4),
            "ml_component": round(ml_component, 4),
            "dl_component": round(dl_component, 4),
            "regime_component": round(regime_component, 4),
        },
    }
