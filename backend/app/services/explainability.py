from __future__ import annotations


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _resolved_signal_confidence(result: dict) -> tuple[str, float]:
    ensemble = result.get("ensemble_output") or {}
    ensemble_signal = str(ensemble.get("signal") or "").upper().strip()
    if ensemble_signal in {"BUY", "SELL", "HOLD"}:
        return ensemble_signal, _safe_float(ensemble.get("confidence"), _safe_float(result.get("confidence"), 0.0))
    signal = str(result.get("enhanced_signal", result.get("signal", "HOLD"))).upper().strip()
    if signal not in {"BUY", "SELL", "HOLD"}:
        signal = "HOLD"
    return signal, _safe_float(result.get("confidence"), 0.0)


def _confidence_band(confidence: float) -> str:
    if confidence >= 75:
        return "strong"
    if confidence >= 58:
        return "moderate"
    return "low"


def _build_summary(signal: str, confidence: float, technical_note: str, drivers: list[str]) -> str:
    band = _confidence_band(confidence)
    concise_drivers = [
        item.strip().rstrip(".")
        for item in drivers
        if str(item or "").strip() and not str(item).strip().lower().startswith("ensemble context:")
    ]
    if concise_drivers:
        joined = "; ".join(concise_drivers[:2])
        return f"{signal} ({confidence:.0f}% {band}) — technical alignment {technical_note}; {joined}."
    return f"{signal} ({confidence:.0f}% {band}) — technical alignment {technical_note}; no dominant external driver."


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

    signal, confidence = _resolved_signal_confidence(result)
    supporting = []
    contradictory = []
    invalidators = []

    technical_score = _safe_float(result.get("technical_score"), 0.0)
    mtf_score = _safe_float(result.get("mtf_score"), 0.0)
    rs_score = _safe_float(result.get("rs_score"), 0.0)
    trend_quality_score = _safe_float(result.get("trend_quality_score"), 0.0)
    ml_output = result.get("ml_output") or {}
    dl_output = result.get("dl_output") or {}
    news_items = result.get("news_items") or []

    if technical_score >= 1:
        supporting.append(f"Technical score supports continuation ({technical_score:.1f}).")
        technical_note = "supports continuation"
    elif technical_score <= -1:
        contradictory.append(f"Technical score is defensive ({technical_score:.1f}).")
        technical_note = "is defensive"
    else:
        technical_note = "is neutral"

    if mtf_score > 0:
        supporting.append(f"Multi-timeframe alignment is positive ({mtf_score:.1f}).")
    elif mtf_score < 0:
        contradictory.append(f"Multi-timeframe alignment is weak ({mtf_score:.1f}).")

    if rs_score > 0:
        supporting.append(f"Relative strength is positive ({rs_score:.1f}).")
    elif rs_score < 0:
        contradictory.append(f"Relative strength is lagging ({rs_score:.1f}).")

    if trend_quality_score > 0:
        supporting.append(f"Trend quality is supportive ({trend_quality_score:.1f}).")
    elif trend_quality_score < 0:
        contradictory.append(f"Trend quality is deteriorating ({trend_quality_score:.1f}).")

    candle_signal = str(result.get("candle_signal") or "").strip().upper()
    if candle_signal and candle_signal not in {"NONE", "NEUTRAL"}:
        supporting.append(f"Candle context includes {candle_signal.replace('_', ' ').title()}.")

    if result.get("squeeze_ready"):
        supporting.append("Squeeze / breakout readiness is active.")

    if news_items:
        lead_news = news_items[0]
        news_tone = str(lead_news.get("sentiment") or "").upper()
        news_event = str(lead_news.get("event_type") or "general").replace("_", " ")
        relation = str(lead_news.get("event_relation") or "").strip().lower()
        if news_tone == "POSITIVE":
            supporting.append(f"News flow is supportive ({news_event}).")
            if relation == "event_update":
                supporting.append("Headline is an update to an existing event, reducing novelty risk.")
        elif news_tone == "NEGATIVE":
            contradictory.append(f"News flow is adverse ({news_event}).")
            if relation == "event_update":
                contradictory.append("Negative event update raises continuation risk.")

    if isinstance(ml_output, dict) and not ml_output.get("error"):
        prob_buy = _safe_float(ml_output.get("prob_buy"), 0.0)
        prob_sell = _safe_float(ml_output.get("prob_sell"), 0.0)
        if prob_buy > prob_sell and prob_buy >= 0.45:
            supporting.append(f"ML ranking leans long (buy {prob_buy:.2f} vs sell {prob_sell:.2f}).")
        elif prob_sell > prob_buy and prob_sell >= 0.45:
            contradictory.append(f"ML ranking leans defensive (sell {prob_sell:.2f} vs buy {prob_buy:.2f}).")

    if isinstance(dl_output, dict) and not dl_output.get("error"):
        dl_buy = _safe_float(dl_output.get("prob_buy"), 0.0)
        dl_sell = _safe_float(dl_output.get("prob_sell"), 0.0)
        if abs(dl_buy - dl_sell) >= 0.18:
            dominant = "long" if dl_buy > dl_sell else "defensive"
            supporting.append(f"DL path supports a {dominant} tilt ({max(dl_buy, dl_sell):.2f}).")

    if confidence < 55:
        invalidators.append("Confidence is modest; treat this as a watch-first setup.")
    if signal == "BUY" and (mtf_score < 0 or rs_score < 0):
        invalidators.append("BUY thesis weakens if multi-timeframe or relative-strength inputs continue to soften.")
    if signal == "SELL" and (mtf_score > 0 or rs_score > 0):
        invalidators.append("SELL thesis weakens if higher-timeframe support returns.")
    if signal == "HOLD":
        invalidators.append("HOLD can transition quickly if trend quality or score expands.")

    ensemble = result.get("ensemble_output") or {}
    if isinstance(ensemble, dict) and ensemble.get("reasoning"):
        supporting.append(f"Ensemble context: {ensemble.get('reasoning')}.")

    if not supporting:
        supporting.append("No strong supporting factor cleared the explanation threshold.")
    if not contradictory:
        contradictory.append("No major contradictory factor is dominant right now.")

    summary = _build_summary(signal, confidence, technical_note, supporting + contradictory)

    return {
        "signal": signal,
        "confidence": round(confidence, 2),
        "summary": summary,
        "supporting_factors": supporting[:5],
        "contradictory_factors": contradictory[:5],
        "invalidators": invalidators[:4],
        "confidence_note": "This explanation is conservative and based only on the inputs currently available to the platform.",
    }
