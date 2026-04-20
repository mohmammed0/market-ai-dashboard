from __future__ import annotations

from typing import Any

from backend.app.config import (
    AUTO_TRADING_MIN_AGREEMENT,
    AUTO_TRADING_MIN_ENSEMBLE_SCORE,
    AUTO_TRADING_MIN_SIGNAL_CONFIDENCE,
    AUTO_TRADING_TRADE_DIRECTION,
)
from backend.app.domain.execution.contracts import SignalSnapshot

_ALLOWED_DIRECTIONS = {"both", "long_only", "short_only"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def normalize_auto_trade_direction(value: str | None) -> str:
    normalized = str(value or AUTO_TRADING_TRADE_DIRECTION).strip().lower()
    return normalized if normalized in _ALLOWED_DIRECTIONS else AUTO_TRADING_TRADE_DIRECTION


def resolve_auto_trade_gate_config(auto_trading_config: dict | None = None) -> dict:
    payload = auto_trading_config if isinstance(auto_trading_config, dict) else {}
    return {
        "min_signal_confidence": max(float(payload.get("min_signal_confidence", AUTO_TRADING_MIN_SIGNAL_CONFIDENCE) or 0.0), 0.0),
        "min_ensemble_score": max(float(payload.get("min_ensemble_score", AUTO_TRADING_MIN_ENSEMBLE_SCORE) or 0.0), 0.0),
        "min_agreement": max(float(payload.get("min_agreement", AUTO_TRADING_MIN_AGREEMENT) or 0.0), 0.0),
        "trade_direction": normalize_auto_trade_direction(payload.get("trade_direction")),
    }


def is_auto_executable_signal(signal_snapshot: SignalSnapshot, auto_trading_config: dict | None = None) -> bool:
    """Return True when a directional signal passes configured auto-trade gates."""
    signal = str(signal_snapshot.signal or "").upper().strip()
    if signal not in {"BUY", "SELL"}:
        return False

    gate_config = resolve_auto_trade_gate_config(auto_trading_config)
    confidence = _safe_float(signal_snapshot.confidence, 0.0)
    if confidence < gate_config["min_signal_confidence"]:
        return False

    payload = signal_snapshot.analysis_payload if isinstance(signal_snapshot.analysis_payload, dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    ensemble = analysis.get("ensemble_output") if isinstance(analysis.get("ensemble_output"), dict) else {}

    if ensemble:
        score_magnitude = abs(_safe_float(ensemble.get("ensemble_score"), 0.0))
        if score_magnitude < gate_config["min_ensemble_score"]:
            return False

        agreement_raw = ensemble.get("agreement_ratio")
        if agreement_raw is not None and _safe_float(agreement_raw, 0.0) < gate_config["min_agreement"]:
            return False

    return True
