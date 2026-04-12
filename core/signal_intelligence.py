"""Signal Intelligence Layer — enhances raw engine signals with context-aware scoring.

Sits between analysis_engine outputs and the API layer. Adds:
1. Multi-timeframe trend alignment (daily + weekly signals agree = stronger)
2. Volume confirmation (high volume on signal = more reliable)
3. Momentum quality (RSI + MACD agreement = higher confidence)
4. Risk-adjusted confidence scoring

Does NOT modify analysis_engine or technical_engine — only processes their output.
"""

import logging
from typing import Any

try:
    from app_logger import get_logger
    logger = get_logger("signal_intelligence")
except Exception:
    logger = logging.getLogger("signal_intelligence")


def enhance_signal(analysis_result: dict) -> dict:
    """Add intelligence layer to raw analysis_engine output.

    Adds:
    - signal_confidence: 0-100 score of how reliable the signal is
    - signal_quality: "HIGH" / "MEDIUM" / "LOW"
    - confirmation_factors: list of what supports the signal
    - warning_factors: list of what contradicts the signal
    - enhanced_recommendation: refined recommendation text
    """
    if not analysis_result or analysis_result.get("error"):
        return analysis_result

    result = dict(analysis_result)

    signal = str(result.get("signal", "HOLD")).upper()
    score = float(result.get("score", 0)) if result.get("score") is not None else 0

    # Extract technical indicators
    tech = result.get("technical", {}) or {}
    rsi = _safe_float(tech.get("rsi_14") or tech.get("rsi"))
    macd_signal = str(tech.get("macd_signal", "")).upper()
    bb_position = str(tech.get("bb_position", "")).upper()
    volume_ratio = _safe_float(tech.get("volume_ratio") or tech.get("vol_ratio"), 1.0)
    sma_20 = _safe_float(tech.get("sma_20"))
    sma_50 = _safe_float(tech.get("sma_50"))
    current_price = _safe_float(result.get("current_price") or result.get("close"))

    # Use direct fields if nested "technical" not present
    if rsi is None:
        rsi = _safe_float(result.get("rsi14"))
    if macd_signal == "":
        macd_signal = str(result.get("macd_signal", "")).upper()
    if volume_ratio == 1.0:
        volume_ratio = _safe_float(result.get("volume_ratio"), 1.0)
    if sma_20 is None:
        sma_20 = _safe_float(result.get("ma20"))
    if sma_50 is None:
        sma_50 = _safe_float(result.get("ma50"))

    # Build confidence factors
    confirmations = []
    warnings = []
    confidence_points = 50  # Start at neutral

    # --- Factor 1: RSI alignment ---
    if rsi is not None:
        if signal == "BUY":
            if rsi < 35:
                confirmations.append("RSI في منطقة التشبع البيعي — فرصة ارتداد")
                confidence_points += 12
            elif rsi > 70:
                warnings.append("RSI مرتفع جداً — احتمال تصحيح قريب")
                confidence_points -= 15
            elif 40 <= rsi <= 60:
                confirmations.append("RSI في المنطقة المحايدة — مساحة للصعود")
                confidence_points += 5
        elif signal == "SELL":
            if rsi > 65:
                confirmations.append("RSI في منطقة التشبع الشرائي — ضغط بيعي متوقع")
                confidence_points += 12
            elif rsi < 30:
                warnings.append("RSI منخفض جداً — احتمال ارتداد")
                confidence_points -= 15

    # --- Factor 2: MACD alignment ---
    if macd_signal:
        if signal == "BUY" and macd_signal in ("BUY", "BULLISH"):
            confirmations.append("MACD يؤكد اتجاه الشراء")
            confidence_points += 10
        elif signal == "SELL" and macd_signal in ("SELL", "BEARISH"):
            confirmations.append("MACD يؤكد اتجاه البيع")
            confidence_points += 10
        elif signal != "HOLD" and macd_signal not in ("HOLD", "NEUTRAL", ""):
            warnings.append("MACD يتعارض مع الإشارة")
            confidence_points -= 8

    # --- Factor 3: Volume confirmation ---
    if volume_ratio > 1.5:
        confirmations.append(f"حجم تداول مرتفع ({volume_ratio:.1f}x) — يعزز الإشارة")
        confidence_points += 8
    elif volume_ratio < 0.5:
        warnings.append("حجم تداول منخفض — إشارة ضعيفة")
        confidence_points -= 10

    # --- Factor 4: Trend alignment (price vs SMAs) ---
    if current_price and sma_20 and sma_50:
        above_sma20 = current_price > sma_20
        above_sma50 = current_price > sma_50
        sma20_above_50 = sma_20 > sma_50

        if signal == "BUY":
            if above_sma20 and above_sma50 and sma20_above_50:
                confirmations.append("السعر فوق المتوسطات — اتجاه صاعد واضح")
                confidence_points += 12
            elif not above_sma50:
                warnings.append("السعر تحت المتوسط 50 — الاتجاه العام هابط")
                confidence_points -= 10
        elif signal == "SELL":
            if not above_sma20 and not above_sma50 and not sma20_above_50:
                confirmations.append("السعر تحت المتوسطات — اتجاه هابط واضح")
                confidence_points += 12
            elif above_sma50:
                warnings.append("السعر فوق المتوسط 50 — الاتجاه العام صاعد")
                confidence_points -= 10

    # --- Factor 5: Bollinger Band position ---
    if bb_position:
        if signal == "BUY" and bb_position in ("LOWER", "BELOW_LOWER"):
            confirmations.append("السعر عند الحد السفلي لبولنجر — فرصة ارتداد")
            confidence_points += 8
        elif signal == "SELL" and bb_position in ("UPPER", "ABOVE_UPPER"):
            confirmations.append("السعر عند الحد العلوي لبولنجر — ضغط بيعي")
            confidence_points += 8

    # --- Factor 6: Score magnitude ---
    abs_score = abs(score)
    if abs_score >= 5:
        confirmations.append(f"النتيجة قوية ({score:+.1f}) — إشارة واضحة")
        confidence_points += 10
    elif abs_score <= 1 and signal != "HOLD":
        warnings.append(f"النتيجة ضعيفة ({score:+.1f}) — إشارة مترددة")
        confidence_points -= 12

    # --- Factor 7: ML layer boost ---
    ml_result = result.get("ml_result") or {}
    if not isinstance(ml_result, dict):
        ml_result = {}

    ml_signal = str(ml_result.get("ml_signal", "")).upper()
    ml_confidence = _safe_float(ml_result.get("ml_confidence"))

    # Try top-level ML fields if nested structure not present
    if not ml_signal or ml_signal == "":
        ml_signal = str(result.get("ml_signal", "")).upper()
    if ml_confidence is None:
        ml_confidence = _safe_float(result.get("ml_confidence"))

    if ml_signal and ml_signal == signal and ml_confidence and ml_confidence > 0.6:
        confirmations.append(f"نموذج ML يؤكد ({ml_confidence:.0%} ثقة)")
        confidence_points += 10
    elif ml_signal and ml_signal != signal and ml_signal != "HOLD":
        warnings.append(f"نموذج ML يتعارض — يقترح {ml_signal}")
        confidence_points -= 8

    # --- Factor 8: Multi-timeframe alignment ---
    mtf = result.get("multi_timeframe") or {}
    if mtf:
        daily_signal = str(mtf.get("daily", {}).get("signal", "HOLD")).upper()
        weekly_signal = str(mtf.get("weekly", {}).get("signal", "HOLD")).upper()

        if daily_signal == signal and weekly_signal == signal and signal != "HOLD":
            confirmations.append("توافق متعدد الأطر الزمنية — إشارة قوية جداً")
            confidence_points += 15
        elif daily_signal != signal and weekly_signal != signal:
            warnings.append("عدم توافق بين الأطر الزمنية — اختلاف واضح")
            confidence_points -= 12

    # Clamp confidence
    confidence = max(5, min(95, confidence_points))

    # Quality rating
    if confidence >= 70:
        quality = "HIGH"
    elif confidence >= 45:
        quality = "MEDIUM"
    else:
        quality = "LOW"

    # Enhanced recommendation
    if signal == "HOLD":
        recommendation = "انتظر — لا توجد إشارة واضحة حالياً"
    elif quality == "HIGH":
        action = "شراء" if signal == "BUY" else "بيع"
        recommendation = f"إشارة {action} قوية مدعومة بـ {len(confirmations)} عوامل"
    elif quality == "MEDIUM":
        action = "شراء" if signal == "BUY" else "بيع"
        recommendation = f"إشارة {action} متوسطة — تحقق من التحذيرات"
    else:
        recommendation = "إشارة ضعيفة — لا يُنصح بالتنفيذ حالياً"

    result["signal_confidence"] = confidence
    result["signal_quality"] = quality
    result["confirmation_factors"] = confirmations
    result["warning_factors"] = warnings
    result["enhanced_recommendation"] = recommendation
    result["intelligence_version"] = "1.0"

    return result


def _safe_float(value, default=None):
    """Safely convert value to float, handling None, NaN, and type errors."""
    if value is None:
        return default
    try:
        v = float(value)
        if v != v:  # NaN check
            return default
        return v
    except (ValueError, TypeError):
        return default
