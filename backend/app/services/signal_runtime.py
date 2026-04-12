from __future__ import annotations

from core.analysis_service import analyze_symbol
from core.backtest_service import backtest_symbol_enhanced
from core.ranking_service import rank_analysis

from backend.app.services.dl_lab import infer_sequence
from backend.app.services.ensemble import build_ensemble_output
from backend.app.services.ml_lab import infer_latest


def build_smart_analysis(symbol, start_date, end_date, include_dl=True, include_ensemble=True):
    classic = analyze_symbol(symbol, start_date, end_date)
    if "error" in classic:
        return classic
    ranked = rank_analysis(classic)
    ml_result = infer_latest(symbol, start_date, end_date)
    dl_result = infer_sequence(symbol, start_date, end_date) if include_dl else {"error": "DL inference skipped"}
    ensemble = build_ensemble_output(ranked, ml_result, dl_result) if include_ensemble else None
    ranked["ml_output"] = ml_result
    ranked["dl_output"] = dl_result
    ranked["ensemble_output"] = ensemble
    if isinstance(ensemble, dict):
        ranked["smart_signal"] = ensemble.get("signal")
        ranked["smart_confidence"] = ensemble.get("confidence")
    return ranked


def extract_signal_view(result: dict, mode="classic"):
    mode = str(mode or "classic").lower().strip()
    if not isinstance(result, dict):
        return {"mode": mode, "signal": "HOLD", "confidence": 0.0, "price": None, "reasoning": "invalid result"}

    if mode == "classic":
        signal = str(result.get("enhanced_signal", result.get("signal", "HOLD"))).upper()
        confidence = float(result.get("confidence", 0.0) or 0.0)
        reasoning = result.get("setup_type") or result.get("reasons") or "classic ranked signal"
    elif mode == "ml":
        ml = result.get("ml_output") or {}
        signal = str(ml.get("signal", "HOLD")).upper()
        confidence = float(ml.get("confidence", 0.0) or 0.0)
        reasoning = f"ml probs buy={ml.get('prob_buy', 0)} sell={ml.get('prob_sell', 0)}"
    elif mode == "dl":
        dl = result.get("dl_output") or {}
        signal = str(dl.get("signal", "HOLD")).upper()
        confidence = float(dl.get("confidence", 0.0) or 0.0)
        reasoning = f"dl probs buy={dl.get('prob_buy', 0)} sell={dl.get('prob_sell', 0)}"
    elif mode == "ensemble":
        ensemble = result.get("ensemble_output") or {}
        signal = str(ensemble.get("signal", "HOLD")).upper()
        confidence = float(ensemble.get("confidence", 0.0) or 0.0)
        reasoning = ensemble.get("reasoning") or "ensemble output"
    elif mode == "vectorbt":
        instrument = result.get("instrument") or result.get("symbol")
        start_date = result.get("start_date", "2024-01-01")
        end_date = result.get("end_date", "2026-04-02")
        bt_result = backtest_symbol_enhanced(instrument=instrument, start_date=start_date, end_date=end_date, hold_days=10)
        events = bt_result.get("events", [])
        last_event = events[-1] if events else {}
        signal = str(last_event.get("enhanced_signal", result.get("enhanced_signal", result.get("signal", "HOLD")))).upper()
        confidence = float(bt_result.get("overall_win_rate_pct", result.get("confidence", 0.0)) or 0.0)
        reasoning = "vectorbt-driven paper signal from latest qualified backtest event"
    else:
        signal = str(result.get("signal", "HOLD")).upper()
        confidence = float(result.get("confidence", 0.0) or 0.0)
        reasoning = "fallback signal"

    price = result.get("close")
    if price is None:
        price = (result.get("ml_output") or {}).get("close")
    return {
        "mode": mode,
        "signal": signal,
        "confidence": round(confidence, 4),
        "price": price,
        "reasoning": reasoning,
    }
