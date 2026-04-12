from __future__ import annotations


def build_ml_training_payload(payload) -> dict:
    return {
        "symbols": payload.symbols,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "horizon_days": payload.horizon_days,
        "buy_threshold": payload.buy_threshold,
        "sell_threshold": payload.sell_threshold,
        "run_optuna": payload.run_optuna,
        "trial_count": payload.trial_count,
    }


def build_dl_training_payload(payload) -> dict:
    return {
        "symbols": payload.symbols,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "sequence_length": payload.sequence_length,
        "horizon_days": payload.horizon_days,
        "buy_threshold": payload.buy_threshold,
        "sell_threshold": payload.sell_threshold,
        "epochs": payload.epochs,
        "hidden_size": payload.hidden_size,
        "learning_rate": payload.learning_rate,
    }


def build_training_job_payload(model_type: str, payload) -> dict:
    normalized_type = str(model_type or "ml").strip().lower()
    if normalized_type == "dl":
        return build_dl_training_payload(payload)
    return build_ml_training_payload(payload)
