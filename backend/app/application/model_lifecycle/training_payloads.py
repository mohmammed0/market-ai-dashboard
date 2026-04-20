from __future__ import annotations

from copy import deepcopy

from backend.app.core.date_defaults import training_window_iso


DEFAULT_WORKFLOW_SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY"]


_TRAINING_WORKFLOW_TEMPLATES = [
    {
        "template_id": "ml_baseline",
        "model_type": "ml",
        "label": "ML Baseline",
        "description": "تصنيف يومي متوازن للتحديث السريع والتحقق المستمر.",
        "highlights": ["سريع", "Daily", "Balanced"],
        "defaults": {
            "symbols": DEFAULT_WORKFLOW_SYMBOLS,
            "horizon_days": 5,
            "buy_threshold": 0.02,
            "sell_threshold": -0.02,
            "run_optuna": False,
            "trial_count": 8,
        },
    },
    {
        "template_id": "ml_optuna_swing",
        "model_type": "ml",
        "label": "ML Optuna Swing",
        "description": "بحث أوسع في hyperparameters على نفس تدفق الـ swing trading.",
        "highlights": ["Optuna", "Swing", "Higher fidelity"],
        "defaults": {
            "symbols": DEFAULT_WORKFLOW_SYMBOLS,
            "horizon_days": 7,
            "buy_threshold": 0.025,
            "sell_threshold": -0.025,
            "run_optuna": True,
            "trial_count": 24,
        },
    },
    {
        "template_id": "dl_sequence",
        "model_type": "dl",
        "label": "DL Sequence",
        "description": "نموذج تسلسلي قصير مناسب لإشارات multi-day مع تكلفة تدريب معقولة.",
        "highlights": ["Sequence", "LSTM-ready", "Short horizon"],
        "defaults": {
            "symbols": DEFAULT_WORKFLOW_SYMBOLS,
            "sequence_length": 20,
            "horizon_days": 5,
            "buy_threshold": 0.02,
            "sell_threshold": -0.02,
            "epochs": 8,
            "hidden_size": 48,
            "learning_rate": 0.001,
        },
    },
    {
        "template_id": "dl_regime",
        "model_type": "dl",
        "label": "DL Regime",
        "description": "نافذة أطول وحجم hidden أكبر قليلًا لتحمل تغيّر النظام السوقي.",
        "highlights": ["Longer context", "Regime aware", "Higher compute"],
        "defaults": {
            "symbols": DEFAULT_WORKFLOW_SYMBOLS,
            "sequence_length": 32,
            "horizon_days": 7,
            "buy_threshold": 0.025,
            "sell_threshold": -0.025,
            "epochs": 10,
            "hidden_size": 64,
            "learning_rate": 0.0008,
        },
    },
]


def _normalize_model_type(model_type: str | None) -> str:
    normalized = str(model_type or "ml").strip().lower()
    return "dl" if normalized == "dl" else "ml"


def _normalize_symbols(symbols: list[str] | None) -> list[str]:
    values = [str(item or "").strip().upper() for item in (symbols or []) if str(item or "").strip()]
    return values or list(DEFAULT_WORKFLOW_SYMBOLS)


def _template_payload(template: dict) -> dict:
    start_date, end_date = training_window_iso()
    defaults = deepcopy(template.get("defaults") or {})
    defaults["symbols"] = _normalize_symbols(defaults.get("symbols"))
    defaults["start_date"] = str(defaults.get("start_date") or start_date)
    defaults["end_date"] = str(defaults.get("end_date") or end_date)
    return defaults


def _template_view(template: dict) -> dict:
    return {
        "template_id": template["template_id"],
        "model_type": template["model_type"],
        "label": template["label"],
        "description": template["description"],
        "highlights": list(template.get("highlights") or []),
        "defaults": _template_payload(template),
    }


def list_training_workflow_templates(model_type: str | None = None) -> dict:
    normalized_type = _normalize_model_type(model_type) if model_type else None
    items = [
        _template_view(template)
        for template in _TRAINING_WORKFLOW_TEMPLATES
        if normalized_type is None or template["model_type"] == normalized_type
    ]
    return {
        "items": items,
        "count": len(items),
        "default_template_id": items[0]["template_id"] if items else None,
    }


def _find_template(template_id: str | None, model_type: str) -> dict:
    normalized_type = _normalize_model_type(model_type)
    normalized_template_id = str(template_id or "").strip().lower()
    for template in _TRAINING_WORKFLOW_TEMPLATES:
        if normalized_template_id and template["template_id"] == normalized_template_id:
            if template["model_type"] != normalized_type:
                raise ValueError(
                    f"Template {template['template_id']} is for {template['model_type']}, not {normalized_type}."
                )
            return template
    for template in _TRAINING_WORKFLOW_TEMPLATES:
        if template["model_type"] == normalized_type:
            return template
    raise ValueError(f"No training workflow template available for model type: {model_type}")


def build_ml_training_payload(payload: dict) -> dict:
    return {
        "symbols": payload["symbols"],
        "start_date": payload["start_date"],
        "end_date": payload["end_date"],
        "horizon_days": payload["horizon_days"],
        "buy_threshold": payload["buy_threshold"],
        "sell_threshold": payload["sell_threshold"],
        "run_optuna": payload["run_optuna"],
        "trial_count": payload["trial_count"],
    }


def build_dl_training_payload(payload: dict) -> dict:
    return {
        "symbols": payload["symbols"],
        "start_date": payload["start_date"],
        "end_date": payload["end_date"],
        "sequence_length": payload["sequence_length"],
        "horizon_days": payload["horizon_days"],
        "buy_threshold": payload["buy_threshold"],
        "sell_threshold": payload["sell_threshold"],
        "epochs": payload["epochs"],
        "hidden_size": payload["hidden_size"],
        "learning_rate": payload["learning_rate"],
    }


def resolve_training_job_config(model_type: str, payload) -> dict:
    normalized_type = _normalize_model_type(model_type)
    template = _find_template(getattr(payload, "template_id", None), normalized_type)
    resolved = _template_payload(template)
    resolved.update(
        {
            "symbols": _normalize_symbols(getattr(payload, "symbols", None) or resolved.get("symbols")),
            "start_date": str(getattr(payload, "start_date", None) or resolved["start_date"]),
            "end_date": str(getattr(payload, "end_date", None) or resolved["end_date"]),
            "horizon_days": int(getattr(payload, "horizon_days", None) or resolved["horizon_days"]),
            "buy_threshold": float(getattr(payload, "buy_threshold", None) if getattr(payload, "buy_threshold", None) is not None else resolved["buy_threshold"]),
            "sell_threshold": float(getattr(payload, "sell_threshold", None) if getattr(payload, "sell_threshold", None) is not None else resolved["sell_threshold"]),
            "run_optuna": bool(getattr(payload, "run_optuna", resolved.get("run_optuna", False))),
            "trial_count": int(getattr(payload, "trial_count", None) or resolved.get("trial_count", 10)),
            "sequence_length": int(getattr(payload, "sequence_length", None) or resolved.get("sequence_length", 20)),
            "epochs": int(getattr(payload, "epochs", None) or resolved.get("epochs", 8)),
            "hidden_size": int(getattr(payload, "hidden_size", None) or resolved.get("hidden_size", 48)),
            "learning_rate": float(getattr(payload, "learning_rate", None) or resolved.get("learning_rate", 0.001)),
        }
    )

    if normalized_type == "dl":
        training_payload = build_dl_training_payload(resolved)
    else:
        training_payload = build_ml_training_payload(resolved)

    return {
        "model_type": normalized_type,
        "template": _template_view(template),
        "payload": training_payload,
    }


def build_training_job_payload(model_type: str, payload) -> dict:
    return resolve_training_job_config(model_type, payload)["payload"]
