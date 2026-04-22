"""Signal Intelligence Layer — enhances raw engine signals with context-aware scoring.

Sits between legacy analysis outputs and the API layer. Adds:
1. Multi-timeframe trend alignment
2. Volume confirmation
3. Momentum quality scoring
4. Risk-adjusted confidence scoring

This module does not modify legacy engines; it enriches their outputs.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def enhance_signal(analysis_result: dict) -> dict:
    """Add intelligence-layer fields to an analysis result."""
    if not analysis_result or analysis_result.get("error"):
        return analysis_result

    result = dict(analysis_result)

    signal = str(result.get("signal", "HOLD")).upper()
    score = float(result.get("score", 0)) if result.get("score") is not None else 0

    tech = result.get("technical", {}) or {}
    rsi = _safe_float(tech.get("rsi_14") or tech.get("rsi"))
    macd_signal = str(tech.get("macd_signal", "")).upper()
    bb_position = str(tech.get("bb_position", "")).upper()
    volume_ratio = _safe_float(tech.get("volume_ratio") or tech.get("vol_ratio"), 1.0)
    sma_20 = _safe_float(tech.get("sma_20"))
    sma_50 = _safe_float(tech.get("sma_50"))
    current_price = _safe_float(result.get("current_price") or result.get("close"))

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

    confirmations: list[str] = []
    warnings: list[str] = []
    confidence_points = 50

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

    if volume_ratio > 1.5:
        confirmations.append(f"حجم تداول مرتفع ({volume_ratio:.1f}x) — يعزز الإشارة")
        confidence_points += 8
    elif volume_ratio < 0.5:
        warnings.append("حجم تداول منخفض — إشارة ضعيفة")
        confidence_points -= 10

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

    if bb_position:
        if signal == "BUY" and bb_position in ("LOWER", "BELOW_LOWER"):
            confirmations.append("السعر عند الحد السفلي لبولنجر — فرصة ارتداد")
            confidence_points += 8
        elif signal == "SELL" and bb_position in ("UPPER", "ABOVE_UPPER"):
            confirmations.append("السعر عند الحد العلوي لبولنجر — ضغط بيعي")
            confidence_points += 8

    abs_score = abs(score)
    if abs_score >= 5:
        confirmations.append(f"النتيجة قوية ({score:+.1f}) — إشارة واضحة")
        confidence_points += 10
    elif abs_score <= 1 and signal != "HOLD":
        warnings.append(f"النتيجة ضعيفة ({score:+.1f}) — إشارة مترددة")
        confidence_points -= 12

    ml_result = result.get("ml_result") or {}
    if not isinstance(ml_result, dict):
        ml_result = {}

    ml_signal = str(ml_result.get("ml_signal", "")).upper()
    ml_confidence = _safe_float(ml_result.get("ml_confidence"))

    if not ml_signal:
        ml_signal = str(result.get("ml_signal", "")).upper()
    if ml_confidence is None:
        ml_confidence = _safe_float(result.get("ml_confidence"))

    if ml_signal and ml_signal == signal and ml_confidence and ml_confidence > 0.6:
        confirmations.append(f"نموذج ML يؤكد ({ml_confidence:.0%} ثقة)")
        confidence_points += 10
    elif ml_signal and ml_signal != signal and ml_signal != "HOLD":
        warnings.append(f"نموذج ML يتعارض — يقترح {ml_signal}")
        confidence_points -= 8

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

    confidence = max(5, min(95, confidence_points))

    if confidence >= 70:
        quality = "HIGH"
    elif confidence >= 45:
        quality = "MEDIUM"
    else:
        quality = "LOW"

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


def _safe_float(value: Any, default=None):
    if value is None:
        return default
    try:
        parsed = float(value)
        if parsed != parsed:
            return default
        return parsed
    except (TypeError, ValueError):
        return default
