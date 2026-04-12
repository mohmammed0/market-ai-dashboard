from __future__ import annotations


def build_signal_explanation(result: dict) -> dict:
    if not isinstance(result, dict):
        return {
            "signal": "HOLD",
            "confidence": 0,
            "summary": "No explanation available.",
            "supporting_factors": [],
            "contradictory_factors": [],
            "invalidators": [],
            "confidence_note": "No structured analysis result was provided.",
        }

    signal = str(result.get("enhanced_signal", result.get("signal", "HOLD"))).upper()
    confidence = float(result.get("confidence", 0.0) or 0.0)
    supporting = []
    contradictory = []
    invalidators = []

    technical_score = float(result.get("technical_score", 0.0) or 0.0)
    mtf_score = float(result.get("mtf_score", 0.0) or 0.0)
    rs_score = float(result.get("rs_score", 0.0) or 0.0)
    trend_quality_score = float(result.get("trend_quality_score", 0.0) or 0.0)

    if technical_score > 0:
        supporting.append(f"Technical score is supportive at {technical_score:.1f}.")
    elif technical_score < 0:
        contradictory.append(f"Technical score is negative at {technical_score:.1f}.")

    if mtf_score > 0:
        supporting.append(f"Multi-timeframe alignment is positive at {mtf_score:.1f}.")
    elif mtf_score < 0:
        contradictory.append(f"Multi-timeframe alignment is weak at {mtf_score:.1f}.")

    if rs_score > 0:
        supporting.append(f"Relative strength is positive at {rs_score:.1f}.")
    elif rs_score < 0:
        contradictory.append(f"Relative strength is lagging at {rs_score:.1f}.")

    if trend_quality_score > 0:
        supporting.append(f"Trend quality is supportive at {trend_quality_score:.1f}.")
    elif trend_quality_score < 0:
        contradictory.append(f"Trend quality is deteriorating at {trend_quality_score:.1f}.")

    candle_signal = str(result.get("candle_signal") or "").strip()
    if candle_signal:
        supporting.append(f"Candle context includes {candle_signal.replace('_', ' ').title()}.")

    if result.get("squeeze_ready"):
        supporting.append("Squeeze / breakout readiness is active.")

    if confidence < 55:
        invalidators.append("Confidence is still modest, so the setup may not survive a small regime change.")
    if signal == "BUY" and (mtf_score < 0 or rs_score < 0):
        invalidators.append("A BUY thesis would weaken if multi-timeframe or relative-strength inputs continue to soften.")
    if signal == "SELL" and (mtf_score > 0 or rs_score > 0):
        invalidators.append("A SELL thesis would weaken if higher-timeframe trend support returns.")
    if signal == "HOLD":
        invalidators.append("A HOLD can quickly transition if either trend quality or combined score improves materially.")

    ensemble = result.get("ensemble_output") or {}
    if isinstance(ensemble, dict) and ensemble.get("reasoning"):
        supporting.append(f"Ensemble context: {ensemble.get('reasoning')}.")

    if not supporting:
        supporting.append("No strong supporting factor cleared the explanation threshold.")
    if not contradictory:
        contradictory.append("No major contradictory factor is dominant right now.")

    return {
        "signal": signal,
        "confidence": round(confidence, 2),
        "summary": f"{signal} with {confidence:.0f} confidence based on the current ranked signal stack.",
        "supporting_factors": supporting[:5],
        "contradictory_factors": contradictory[:5],
        "invalidators": invalidators[:4],
        "confidence_note": "This explanation is conservative and based only on the inputs currently available to the platform.",
    }
