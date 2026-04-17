from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha1

from backtest_engine import backtest_symbol_enhanced
from ranking_engine import _confidence_score

from backend.app.config import (
    CONFIDENCE_CALIBRATION_CACHE_TTL_SECONDS,
    CONFIDENCE_CALIBRATION_ENABLED,
    CONFIDENCE_CALIBRATION_HOLD_DAYS,
    CONFIDENCE_CALIBRATION_LOOKBACK_DAYS,
    CONFIDENCE_CALIBRATION_MIN_SAMPLES,
)
from backend.app.core.date_defaults import recent_end_date_iso
from backend.app.services import get_cache


CONFIDENCE_CALIBRATION_CACHE_KEY_PREFIX = "confidence:calibration:"
CONFIDENCE_CALIBRATION_LATEST_KEY = f"{CONFIDENCE_CALIBRATION_CACHE_KEY_PREFIX}latest"
CONFIDENCE_BANDS: tuple[tuple[int, int], ...] = (
    (0, 40),
    (40, 55),
    (55, 70),
    (70, 85),
    (85, 100),
)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _clamp_confidence(value: object) -> float:
    parsed = _safe_float(value, 0.0)
    if parsed <= 1.0:
        parsed *= 100.0
    return max(0.0, min(parsed, 99.0))


def _normalize_symbols(symbols: list[str] | None) -> list[str]:
    if not symbols:
        return []
    prepared: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        prepared.append(symbol)
        seen.add(symbol)
    return prepared


def _confidence_band_label(confidence: float) -> str:
    for low, high in CONFIDENCE_BANDS:
        if confidence >= low and (confidence < high or (high == 100 and confidence <= 100)):
            return f"{low}-{high}"
    return "85-100"


def _derive_event_action(signal: str, confidence: float) -> str:
    normalized_signal = str(signal or "HOLD").upper().strip()
    if normalized_signal == "BUY":
        return "BUY" if confidence >= 82 else "ADD"
    if normalized_signal == "SELL":
        return "EXIT" if confidence >= 80 else "TRIM"
    return "WATCH"


def _build_profile_cache_key(symbols: list[str], start_date: str, end_date: str) -> str:
    fingerprint_input = "|".join(sorted(symbols)) + f"|{start_date}|{end_date}|{CONFIDENCE_CALIBRATION_HOLD_DAYS}"
    digest = sha1(fingerprint_input.encode("utf-8")).hexdigest()[:12]
    return f"{CONFIDENCE_CALIBRATION_CACHE_KEY_PREFIX}{digest}"


def _aggregate_profile(samples: list[dict], symbols: list[str], start_date: str, end_date: str) -> dict:
    bands: dict[str, dict] = {
        f"{low}-{high}": {
            "samples": 0,
            "wins": 0,
            "avg_predicted_confidence": 0.0,
            "avg_trade_return_pct": 0.0,
            "win_rate_pct": None,
        }
        for low, high in CONFIDENCE_BANDS
    }
    action_groups: dict[str, dict] = defaultdict(
        lambda: {
            "samples": 0,
            "wins": 0,
            "avg_predicted_confidence": 0.0,
            "avg_trade_return_pct": 0.0,
            "win_rate_pct": None,
        }
    )
    symbol_groups: dict[str, dict] = defaultdict(
        lambda: {
            "samples": 0,
            "wins": 0,
            "avg_predicted_confidence": 0.0,
            "avg_trade_return_pct": 0.0,
            "win_rate_pct": None,
        }
    )

    for sample in samples:
        confidence = _clamp_confidence(sample.get("predicted_confidence"))
        band_key = _confidence_band_label(confidence)
        action = str(sample.get("action") or "WATCH").upper()
        symbol = str(sample.get("symbol") or "").upper().strip()
        win = bool(sample.get("win"))
        trade_return = _safe_float(sample.get("trade_return_pct"), 0.0)

        band_row = bands[band_key]
        band_row["samples"] += 1
        band_row["wins"] += int(win)
        band_row["avg_predicted_confidence"] += confidence
        band_row["avg_trade_return_pct"] += trade_return

        action_row = action_groups[action]
        action_row["samples"] += 1
        action_row["wins"] += int(win)
        action_row["avg_predicted_confidence"] += confidence
        action_row["avg_trade_return_pct"] += trade_return

        symbol_row = symbol_groups[symbol]
        symbol_row["samples"] += 1
        symbol_row["wins"] += int(win)
        symbol_row["avg_predicted_confidence"] += confidence
        symbol_row["avg_trade_return_pct"] += trade_return

    for target in (bands, action_groups, symbol_groups):
        for row in target.values():
            sample_count = int(row.get("samples") or 0)
            if sample_count <= 0:
                continue
            row["avg_predicted_confidence"] = round(
                _safe_float(row.get("avg_predicted_confidence"), 0.0) / sample_count,
                2,
            )
            row["avg_trade_return_pct"] = round(
                _safe_float(row.get("avg_trade_return_pct"), 0.0) / sample_count,
                4,
            )
            row["win_rate_pct"] = round((int(row.get("wins") or 0) * 100.0) / sample_count, 2)

    high_confidence_samples = [sample for sample in samples if _clamp_confidence(sample.get("predicted_confidence")) >= 80.0]
    high_confidence_win_rate = None
    high_confidence_avg_predicted = None
    high_confidence_avg_return = None
    high_confidence_gap = None
    if high_confidence_samples:
        total = len(high_confidence_samples)
        wins = sum(1 for sample in high_confidence_samples if bool(sample.get("win")))
        avg_pred = sum(_clamp_confidence(sample.get("predicted_confidence")) for sample in high_confidence_samples) / total
        avg_ret = sum(_safe_float(sample.get("trade_return_pct"), 0.0) for sample in high_confidence_samples) / total
        high_confidence_win_rate = round((wins * 100.0) / total, 2)
        high_confidence_avg_predicted = round(avg_pred, 2)
        high_confidence_avg_return = round(avg_ret, 4)
        high_confidence_gap = round(high_confidence_avg_predicted - high_confidence_win_rate, 2)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "enabled": True,
        "window": {
            "start_date": start_date,
            "end_date": end_date,
            "lookback_days": CONFIDENCE_CALIBRATION_LOOKBACK_DAYS,
            "hold_days": CONFIDENCE_CALIBRATION_HOLD_DAYS,
        },
        "symbols": symbols,
        "samples_count": len(samples),
        "min_samples_required": CONFIDENCE_CALIBRATION_MIN_SAMPLES,
        "bands": dict(bands),
        "actions": dict(action_groups),
        "symbols_stats": dict(symbol_groups),
        "high_confidence": {
            "samples": len(high_confidence_samples),
            "avg_predicted_confidence": high_confidence_avg_predicted,
            "win_rate_pct": high_confidence_win_rate,
            "avg_trade_return_pct": high_confidence_avg_return,
            "overconfidence_gap_pct": high_confidence_gap,
        },
        "status": "ready" if len(samples) >= CONFIDENCE_CALIBRATION_MIN_SAMPLES else "insufficient_data",
    }


def _compute_profile(symbols: list[str], start_date: str, end_date: str) -> dict:
    samples: list[dict] = []
    normalized_symbols = _normalize_symbols(symbols)
    if not normalized_symbols:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "status": "insufficient_data",
            "window": {"start_date": start_date, "end_date": end_date},
            "symbols": [],
            "samples_count": 0,
            "bands": {},
            "actions": {},
            "symbols_stats": {},
            "high_confidence": {},
        }

    for symbol in normalized_symbols:
        result = backtest_symbol_enhanced(
            instrument=symbol,
            start_date=start_date,
            end_date=end_date,
            hold_days=CONFIDENCE_CALIBRATION_HOLD_DAYS,
            min_technical_score=2,
            buy_score_threshold=3,
            sell_score_threshold=4,
        )
        events = result.get("events") if isinstance(result, dict) else None
        if not isinstance(events, list):
            continue
        for event in events:
            signal = str(event.get("enhanced_signal") or "").upper().strip()
            if signal not in {"BUY", "SELL"}:
                continue
            predicted_confidence = _clamp_confidence(_confidence_score(event))
            action = _derive_event_action(signal, predicted_confidence)
            samples.append(
                {
                    "symbol": symbol,
                    "signal": signal,
                    "action": action,
                    "predicted_confidence": predicted_confidence,
                    "win": bool(event.get("win")),
                    "trade_return_pct": _safe_float(event.get("trade_return_pct"), 0.0),
                }
            )

    return _aggregate_profile(samples, normalized_symbols, start_date, end_date)


def build_and_cache_confidence_calibration_profile(
    symbols: list[str] | None,
    *,
    end_date: str | None = None,
    force_refresh: bool = False,
) -> dict:
    if not CONFIDENCE_CALIBRATION_ENABLED:
        return {"enabled": False, "status": "disabled"}

    normalized_symbols = _normalize_symbols(symbols)
    resolved_end_date = str(end_date or recent_end_date_iso())
    resolved_start_date = (
        datetime.fromisoformat(resolved_end_date).date() - timedelta(days=CONFIDENCE_CALIBRATION_LOOKBACK_DAYS)
    ).isoformat()
    cache = get_cache()
    cache_key = _build_profile_cache_key(normalized_symbols, resolved_start_date, resolved_end_date)

    def factory() -> dict:
        profile = _compute_profile(normalized_symbols, resolved_start_date, resolved_end_date)
        cache.set(CONFIDENCE_CALIBRATION_LATEST_KEY, profile, ttl_seconds=CONFIDENCE_CALIBRATION_CACHE_TTL_SECONDS)
        return profile

    if force_refresh:
        profile = factory()
        cache.set(cache_key, profile, ttl_seconds=CONFIDENCE_CALIBRATION_CACHE_TTL_SECONDS)
        return profile
    return cache.get_or_set(cache_key, factory, ttl_seconds=CONFIDENCE_CALIBRATION_CACHE_TTL_SECONDS)


def get_latest_confidence_calibration_profile() -> dict | None:
    if not CONFIDENCE_CALIBRATION_ENABLED:
        return None
    profile = get_cache().get(CONFIDENCE_CALIBRATION_LATEST_KEY)
    if isinstance(profile, dict) and profile.get("enabled"):
        return profile
    return None


def calibrate_confidence(raw_confidence: object, signal: str, profile: dict | None, symbol: str | None = None) -> float:
    raw = _clamp_confidence(raw_confidence)
    normalized_signal = str(signal or "HOLD").upper().strip()
    if not isinstance(profile, dict):
        return raw
    if profile.get("status") != "ready":
        return raw

    bands = profile.get("bands") or {}
    band_key = _confidence_band_label(raw)
    band_row = bands.get(band_key) if isinstance(bands, dict) else None
    band_samples = int((band_row or {}).get("samples") or 0)
    band_empirical = _safe_float((band_row or {}).get("win_rate_pct"), raw)

    action_key = _derive_event_action("BUY" if normalized_signal == "BUY" else "SELL" if normalized_signal == "SELL" else "HOLD", raw)
    actions = profile.get("actions") or {}
    action_row = actions.get(action_key) if isinstance(actions, dict) else None
    action_samples = int((action_row or {}).get("samples") or 0)
    action_empirical = _safe_float((action_row or {}).get("win_rate_pct"), band_empirical)

    total_samples = int(profile.get("samples_count") or 0)
    if total_samples < CONFIDENCE_CALIBRATION_MIN_SAMPLES:
        return raw

    sample_strength = min(1.0, band_samples / max(float(CONFIDENCE_CALIBRATION_MIN_SAMPLES), 1.0))
    action_strength = min(1.0, action_samples / max(float(CONFIDENCE_CALIBRATION_MIN_SAMPLES), 1.0))

    blended_empirical = (
        band_empirical * (0.70 + (0.15 * sample_strength))
        + action_empirical * (0.30 + (0.20 * action_strength))
    ) / (
        (0.70 + (0.15 * sample_strength))
        + (0.30 + (0.20 * action_strength))
    )
    symbol_strength = 0.0
    symbols_stats = profile.get("symbols_stats") or {}
    if symbol and isinstance(symbols_stats, dict):
        symbol_row = symbols_stats.get(str(symbol).upper().strip())
        if isinstance(symbol_row, dict):
            symbol_samples = int(symbol_row.get("samples") or 0)
            symbol_empirical = _safe_float(symbol_row.get("win_rate_pct"), blended_empirical)
            if symbol_samples >= max(6, CONFIDENCE_CALIBRATION_MIN_SAMPLES // 2):
                symbol_strength = min(1.0, symbol_samples / max(float(CONFIDENCE_CALIBRATION_MIN_SAMPLES), 1.0))
                blended_empirical = (
                    blended_empirical * (1.0 - (0.35 * symbol_strength))
                    + symbol_empirical * (0.35 * symbol_strength)
                )

    empirical_weight = (0.24 + (0.12 if raw >= 80 else 0.0)) * max(sample_strength, 0.35)
    if symbol_strength > 0.0:
        empirical_weight *= (1.0 - (0.25 * symbol_strength))
    calibrated = (raw * (1.0 - empirical_weight)) + (blended_empirical * empirical_weight)

    overconfidence_gap = raw - blended_empirical
    if raw >= 80 and overconfidence_gap > 10:
        penalty_strength = max(sample_strength, 0.40)
        if symbol_strength > 0.0:
            penalty_strength *= (1.0 - (0.30 * symbol_strength))
        calibrated -= min(10.0, overconfidence_gap * 0.28) * penalty_strength

    if normalized_signal in {"BUY", "SELL"} and raw >= 80 and blended_empirical >= 70:
        calibrated = max(calibrated, 70.0)
    elif normalized_signal in {"BUY", "SELL"} and raw >= 75 and blended_empirical >= 62:
        calibrated = max(calibrated, 62.0)
    if normalized_signal == "HOLD":
        calibrated = min(calibrated, 70.0)

    return round(max(0.0, min(calibrated, 99.0)), 2)


def apply_confidence_calibration_to_analysis(analysis: dict, profile: dict | None) -> dict:
    if not isinstance(analysis, dict):
        return analysis
    if not isinstance(profile, dict) or profile.get("status") != "ready":
        analysis["confidence_calibration"] = {
            "enabled": bool(CONFIDENCE_CALIBRATION_ENABLED),
            "applied": False,
            "profile_status": None if profile is None else profile.get("status"),
        }
        return analysis

    classic_signal = str(analysis.get("enhanced_signal") or analysis.get("signal") or "HOLD").upper().strip()
    classic_raw = _clamp_confidence(analysis.get("confidence"))
    resolved_symbol = str(analysis.get("instrument") or analysis.get("symbol") or "").upper().strip() or None
    classic_calibrated = calibrate_confidence(classic_raw, classic_signal, profile, symbol=resolved_symbol)
    analysis["confidence"] = classic_calibrated

    ensemble_payload = analysis.get("ensemble_output") if isinstance(analysis.get("ensemble_output"), dict) else None
    ensemble_raw = None
    ensemble_calibrated = None
    if ensemble_payload is not None:
        ensemble_signal = str(ensemble_payload.get("signal") or classic_signal).upper().strip()
        ensemble_raw = _clamp_confidence(ensemble_payload.get("confidence"))
        ensemble_calibrated = calibrate_confidence(ensemble_raw, ensemble_signal, profile, symbol=resolved_symbol)
        ensemble_payload["confidence"] = ensemble_calibrated

    analysis["confidence_calibration"] = {
        "enabled": True,
        "applied": True,
        "generated_at": profile.get("generated_at"),
        "profile_status": profile.get("status"),
        "classic": {
            "signal": classic_signal,
            "raw_confidence": round(classic_raw, 2),
            "calibrated_confidence": round(classic_calibrated, 2),
        },
        "ensemble": {
            "raw_confidence": None if ensemble_raw is None else round(ensemble_raw, 2),
            "calibrated_confidence": None if ensemble_calibrated is None else round(ensemble_calibrated, 2),
        },
        "symbol_samples": None
        if resolved_symbol is None
        else ((profile.get("symbols_stats") or {}).get(resolved_symbol, {}) or {}).get("samples"),
    }
    return analysis
