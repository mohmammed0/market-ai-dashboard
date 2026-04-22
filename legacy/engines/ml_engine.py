from backend.app.services.ml_lab import infer_latest as infer_ml_run_latest
from legacy.support.app_logger import get_logger


logger = get_logger("ml_engine")


def _class_from_signal(signal: str) -> int:
    normalized = str(signal or "HOLD").upper()
    if normalized == "BUY":
        return 1
    if normalized == "SELL":
        return -1
    return 0


def predict_latest(instrument="AAPL", start_date="2024-01-01", end_date="2026-04-02"):
    instrument = str(instrument or "AAPL").upper().strip()
    result = infer_ml_run_latest(symbol=instrument, start_date=start_date, end_date=end_date)
    if result.get("error"):
        return result

    signal = str(result.get("signal", "HOLD")).upper()
    payload = {
        "instrument": instrument,
        "ml_class": _class_from_signal(signal),
        "ml_signal": signal,
        "ml_confidence": result.get("confidence"),
        "ml_prob_sell": result.get("prob_sell"),
        "ml_prob_hold": result.get("prob_hold"),
        "ml_prob_buy": result.get("prob_buy"),
        "date": result.get("as_of"),
        "close": result.get("close"),
        "run_id": result.get("run_id"),
        "model_resolution": result.get("model_resolution"),
    }

    logger.info(
        "ML predict | instrument=%s | class=%s | signal=%s | confidence=%s | resolution=%s",
        instrument,
        payload["ml_class"],
        payload["ml_signal"],
        payload["ml_confidence"],
        payload["model_resolution"],
    )
    return payload
