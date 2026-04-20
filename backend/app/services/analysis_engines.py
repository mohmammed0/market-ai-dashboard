from __future__ import annotations

from typing import Any

from backend.app.config import AUTO_TRADING_STRATEGY_MODE, LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL
from backend.app.services.auto_trading_diagnostics import get_latest_auto_trading_cycle_diagnostics
from backend.app.services.kronos_intelligence import kronos_status
from backend.app.services.model_artifact_runtime import resolve_model_artifact
from backend.app.services.runtime_settings import get_auto_trading_config

try:
    from backend.app.services.dl_lab import torch as _dl_torch
except Exception:  # pragma: no cover
    _dl_torch = None


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text not in {"0", "false", "no", "off"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _normalize_strategy_mode(config: dict | None = None) -> str:
    settings = config if isinstance(config, dict) else get_auto_trading_config()
    normalized = str(settings.get("strategy_mode") or AUTO_TRADING_STRATEGY_MODE or "ensemble").strip().lower()
    return normalized if normalized in {"classic", "ml", "dl", "ensemble"} else "ensemble"


def _dl_enabled(config: dict | None = None) -> bool:
    strategy_mode = _normalize_strategy_mode(config)
    return bool(LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL or strategy_mode in {"dl", "ensemble"})


def _model_status(model_type: str, *, enabled: bool) -> dict:
    resolved = resolve_model_artifact(model_type)
    if resolved.get("error"):
        return {
            "enabled": bool(enabled),
            "ready": False,
            "model_loaded": False,
            "run_id": None,
            "model_name": None,
            "resolution": None,
            "artifact_path": None,
            "last_error": str(resolved.get("error") or "artifact_unavailable"),
            "fallback_used": False,
            "status_reason": "artifact_unavailable",
        }

    resolution = str(resolved.get("resolution") or "unknown").strip().lower() or None
    fallback_used = resolution not in {"active", "explicit"}
    status_reason = "ready"
    if fallback_used:
        status_reason = f"using_{resolution}_artifact_fallback"

    return {
        "enabled": bool(enabled),
        "ready": bool(enabled),
        "model_loaded": bool(enabled),
        "run_id": resolved.get("run_id"),
        "model_name": resolved.get("model_name"),
        "resolution": resolution,
        "artifact_path": resolved.get("artifact_path"),
        "last_error": None,
        "fallback_used": fallback_used,
        "status_reason": status_reason,
    }


def _latest_cycle_usage(latest_cycle: dict | None) -> dict:
    cycle = latest_cycle if isinstance(latest_cycle, dict) else {}
    summary = cycle.get("summary_counts") if isinstance(cycle.get("summary_counts"), dict) else {}
    rows = cycle.get("rows") if isinstance(cycle.get("rows"), list) else []

    example_dl = None
    example_kronos = None
    example_combined = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if example_dl is None and bool(row.get("dl_contributed")):
            example_dl = row.get("symbol")
        if example_kronos is None and bool(row.get("kronos_contributed")):
            example_kronos = row.get("symbol")
        if example_combined is None and (bool(row.get("dl_contributed")) or bool(row.get("kronos_contributed"))):
            example_combined = {
                "symbol": row.get("symbol"),
                "analysis_signal": row.get("analysis_signal"),
                "ml_signal": row.get("ml_signal"),
                "dl_signal": row.get("dl_signal"),
                "dl_contributed": bool(row.get("dl_contributed")),
                "dl_contribution_to_score": row.get("dl_contribution_to_score"),
                "dl_reason_not_used": row.get("dl_reason_not_used"),
                "kronos_contributed": bool(row.get("kronos_contributed")),
                "kronos_contribution_to_score": row.get("kronos_contribution_to_score"),
                "kronos_reason_not_used": row.get("kronos_reason_not_used"),
                "ensemble_components_used": row.get("ensemble_components_used"),
                "ensemble_components_skipped": row.get("ensemble_components_skipped"),
            }

    return {
        "cycle_id": cycle.get("cycle_id"),
        "rows_count": _safe_int(cycle.get("rows_count"), len(rows)),
        "classic_used_count": _safe_int(summary.get("classic_used_count"), 0),
        "ranking_used_count": _safe_int(summary.get("ranking_used_count"), 0),
        "ml_used_count": _safe_int(summary.get("ml_used_count"), 0),
        "dl_used_count": _safe_int(summary.get("dl_used_count"), 0),
        "kronos_used_count": _safe_int(summary.get("kronos_used_count"), 0),
        "dl_fallback_count": _safe_int(summary.get("dl_fallback_count"), 0),
        "kronos_fallback_count": _safe_int(summary.get("kronos_fallback_count"), 0),
        "symbols_with_dl_contribution": _safe_int(summary.get("symbols_with_dl_contribution"), 0),
        "symbols_with_kronos_contribution": _safe_int(summary.get("symbols_with_kronos_contribution"), 0),
        "example_symbol_with_dl": example_dl,
        "example_symbol_with_kronos": example_kronos,
        "example_engine_contribution": example_combined,
    }


def get_analysis_engines_status(*, latest_cycle: dict | None = None, latest_nonempty: bool = True) -> dict:
    config = get_auto_trading_config()
    strategy_mode = _normalize_strategy_mode(config)
    dl_enabled = _dl_enabled(config)
    ml_status = _model_status("ml", enabled=True)
    dl_status = _model_status("dl", enabled=dl_enabled)
    kronos_runtime = kronos_status(auto_config=config)

    if not dl_enabled:
        dl_status.update(
            {
                "ready": False,
                "model_loaded": False,
                "status_reason": "runtime_disabled_by_strategy_mode",
            }
        )
    elif _dl_torch is None:
        dl_status.update(
            {
                "ready": False,
                "model_loaded": False,
                "last_error": "torch_not_installed",
                "status_reason": "missing_torch_dependency",
            }
        )

    cycle = latest_cycle if isinstance(latest_cycle, dict) else get_latest_auto_trading_cycle_diagnostics(
        include_details=False,
        include_model_breakdown=False,
        include_raw=False,
        latest_nonempty=latest_nonempty,
    )
    usage = _latest_cycle_usage(cycle)

    return {
        "strategy_mode": strategy_mode,
        "classic": {
            "enabled": True,
            "ready": True,
            "status_reason": "core_analysis_pipeline",
        },
        "ranking": {
            "enabled": True,
            "ready": True,
            "status_reason": "ranking_engine_pipeline",
        },
        "ml": ml_status,
        "dl": {
            **dl_status,
            "torch_available": _dl_torch is not None,
        },
        "kronos": {
            "enabled": _safe_bool(kronos_runtime.get("kronos_enabled"), False),
            "ready": _safe_bool(kronos_runtime.get("kronos_ready"), False),
            "loaded": _safe_bool(kronos_runtime.get("kronos_loaded"), False),
            "model_name": kronos_runtime.get("kronos_model_name"),
            "device": kronos_runtime.get("kronos_device"),
            "last_error": kronos_runtime.get("kronos_error") or kronos_runtime.get("kronos_last_error"),
            "status_reason": (
                "shared_ready"
                if _safe_bool(kronos_runtime.get("kronos_ready"), False)
                else (kronos_runtime.get("kronos_degraded_reason") or kronos_runtime.get("kronos_error") or "not_ready")
            ),
            "status_source": kronos_runtime.get("kronos_status_source"),
            "batch_cache": kronos_runtime.get("kronos_batch_cache") if isinstance(kronos_runtime.get("kronos_batch_cache"), dict) else {},
        },
        "latest_cycle": usage,
        "latest_cycle_id": usage.get("cycle_id"),
    }
