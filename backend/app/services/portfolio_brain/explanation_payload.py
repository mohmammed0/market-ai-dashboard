"""Chart/explanation payload shaping for portfolio-brain surfaces."""

from __future__ import annotations

from backend.app.services.portfolio_brain.signal_normalization import (
    coerce_date,
    normalize_band,
    safe_float,
    sentiment_tone,
)


def build_chart_plan(analysis: dict, explanation: dict, events: list[dict]) -> dict:
    signal = str(analysis.get("enhanced_signal") or analysis.get("signal") or "HOLD").upper()
    close = safe_float(analysis.get("close"))
    atr = abs(safe_float(analysis.get("atr14"), 0.0) or 0.0)
    support = safe_float(analysis.get("support"))
    resistance = safe_float(analysis.get("resistance"))
    atr_stop = safe_float(analysis.get("atr_stop"))
    atr_target = safe_float(analysis.get("atr_target"))
    analysis_date = coerce_date(analysis.get("date"))
    zones: list[dict] = []
    levels: list[dict] = []
    markers: list[dict] = []

    if close is not None:
        if signal == "BUY":
            entry = normalize_band(
                support if support is not None else close - (atr * 0.4),
                close,
            )
            target = normalize_band(
                close + (atr * 0.35),
                resistance if resistance is not None else atr_target if atr_target is not None else close + (atr * 1.2),
            )
        elif signal == "SELL":
            entry = normalize_band(
                close,
                resistance if resistance is not None else close + (atr * 0.4),
            )
            target = normalize_band(
                support if support is not None else close - (atr * 1.2),
                close - (atr * 0.35),
            )
        else:
            entry = normalize_band(close - (atr * 0.25), close + (atr * 0.25))
            target = normalize_band(
                support if support is not None else close - (atr * 0.5),
                resistance if resistance is not None else close + (atr * 0.5),
            )

        if entry is not None:
            zones.append(
                {
                    "kind": "entry_zone",
                    "label": "منطقة الدخول",
                    "tone": "accent" if signal == "BUY" else "warning" if signal == "SELL" else "subtle",
                    "low": entry[0],
                    "high": entry[1],
                    "source": "derived_from_close_support_resistance_atr",
                }
            )
        if target is not None:
            zones.append(
                {
                    "kind": "target_zone",
                    "label": "منطقة الهدف",
                    "tone": "positive",
                    "low": target[0],
                    "high": target[1],
                    "source": "derived_from_resistance_support_atr_target",
                }
            )

        markers.append(
            {
                "kind": "signal_marker",
                "label": signal,
                "tone": sentiment_tone(signal),
                "date": analysis_date,
                "value": round(close, 4),
                "detail": explanation.get("summary") or analysis.get("reasons"),
            }
        )

    for kind, label, value, tone in (
        ("support", "الدعم", support, "subtle"),
        ("resistance", "المقاومة", resistance, "warning"),
        ("invalidation", "الإبطال / الوقف", atr_stop, "negative"),
        ("target", "هدف ATR", atr_target, "positive"),
    ):
        if value is not None:
            levels.append(
                {
                    "kind": kind,
                    "label": label,
                    "value": round(value, 4),
                    "tone": tone,
                }
            )

    for row in (analysis.get("news_items") or [])[:3]:
        published_at = coerce_date(row.get("published"))
        markers.append(
            {
                "kind": "news_marker",
                "label": row.get("source") or "خبر",
                "tone": sentiment_tone(row.get("sentiment")),
                "date": published_at,
                "value": round(close, 4) if close is not None else None,
                "detail": row.get("title"),
            }
        )

    for row in events[:2]:
        event_date = coerce_date(row.get("event_at"))
        markers.append(
            {
                "kind": "event_marker",
                "label": row.get("event_type") or row.get("title") or "حدث",
                "tone": "subtle",
                "date": event_date,
                "value": round(close, 4) if close is not None else None,
                "detail": row.get("summary") or row.get("description") or row.get("event_type"),
            }
        )

    return {
        "note": "المناطق والمستويات مشتقة من الدعم والمقاومة وATR والإشارة الحالية، وليست توصية مستقلة جديدة.",
        "zones": zones,
        "levels": levels,
        "markers": markers[:6],
    }
