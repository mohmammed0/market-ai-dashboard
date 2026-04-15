from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from backend.app.config import ROOT_DIR
from backend.app.models import ModelPrediction, ModelRun
from backend.app.services.features import FEATURE_COLUMNS, build_feature_frame, create_target_labels
from backend.app.services.market_data import DEFAULT_SYMBOLS, _load_local_csv, persist_feature_snapshot
from backend.app.services.model_artifact_runtime import resolve_model_artifact
from backend.app.services.storage import dumps_json, loads_json, session_scope

try:
    import joblib
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, confusion_matrix, f1_score
except Exception:  # pragma: no cover - optional dependency
    joblib = None
    GradientBoostingClassifier = None
    RandomForestClassifier = None
    LogisticRegression = None
    classification_report = None
    confusion_matrix = None
    f1_score = None

try:
    import optuna
except Exception:  # pragma: no cover - optional dependency
    optuna = None


ARTIFACT_ROOT = ROOT_DIR / "model_artifacts"
ML_RUN_ROOT = ARTIFACT_ROOT / "ml_runs"
ML_RUN_ROOT.mkdir(parents=True, exist_ok=True)


def _dependency_error():
    return {"error": "Missing ML dependencies: scikit-learn/joblib"}


def _build_training_frame(symbols, start_date, end_date, horizon_days, buy_threshold, sell_threshold):
    import logging as _logging
    _btf_logger = _logging.getLogger(__name__)
    parts = []
    for symbol in symbols:
        try:
            raw = _load_local_csv(symbol, start_date, end_date)
            if raw.empty:
                continue
            features = build_feature_frame(raw, instrument=symbol)
            if features.empty:
                continue
            dataset = create_target_labels(
                features,
                horizon_days=horizon_days,
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
            )
            dataset["instrument"] = symbol
            dataset = dataset.dropna(subset=["future_close"]).copy()
            if not dataset.empty:
                parts.append(dataset)
        except Exception as _sym_exc:
            _btf_logger.warning(
                "ml_lab.build_training_frame.symbol_skipped symbol=%s error=%s",
                symbol,
                " ".join(str(_sym_exc).split()) or type(_sym_exc).__name__,
            )
            continue
    if not parts:
        return pd.DataFrame()
    combined = pd.concat(parts, ignore_index=True)
    combined["datetime"] = pd.to_datetime(combined["datetime"], errors="coerce")
    return combined.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)


def _time_splits(df):
    n = len(df)
    train_end = max(int(n * 0.6), 1)
    val_end = max(int(n * 0.8), train_end + 1)
    return df.iloc[:train_end].copy(), df.iloc[train_end:val_end].copy(), df.iloc[val_end:].copy()


def _build_models():
    return {
        "logreg": LogisticRegression(max_iter=400, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_leaf=4,
            random_state=42,
            n_jobs=int(__import__("os").environ.get("MARKET_AI_ML_N_JOBS", "1")),
            class_weight="balanced_subsample",
        ),
        "gradient_boosting": GradientBoostingClassifier(random_state=42),
    }


def _prediction_to_signal(pred_class):
    if int(pred_class) > 0:
        return "BUY"
    if int(pred_class) < 0:
        return "SELL"
    return "HOLD"


def train_baseline_models(
    symbols=None,
    start_date="2020-01-01",
    end_date="2026-04-02",
    horizon_days=5,
    buy_threshold=0.02,
    sell_threshold=-0.02,
    run_optuna=False,
    trial_count=10,
    set_active=True,
):
    if joblib is None or LogisticRegression is None:
        return _dependency_error()

    symbols = [str(symbol).upper().strip() for symbol in (symbols or DEFAULT_SYMBOLS) if str(symbol).strip()]
    df = _build_training_frame(symbols, start_date, end_date, horizon_days, buy_threshold, sell_threshold)
    if df.empty:
        return {"error": "No training rows available from current local data."}

    train_df, val_df, test_df = _time_splits(df)
    if train_df.empty or val_df.empty or test_df.empty:
        return {"error": "Not enough rows for time-based train/validation/test split."}

    X_train = train_df[FEATURE_COLUMNS].copy()
    y_train = train_df["target_class"].astype(int)
    X_val = val_df[FEATURE_COLUMNS].copy()
    y_val = val_df["target_class"].astype(int)
    X_test = test_df[FEATURE_COLUMNS].copy()
    y_test = test_df["target_class"].astype(int)

    models = _build_models()
    if run_optuna and optuna is not None:
        study = optuna.create_study(direction="maximize")

        def objective(trial):
            model = RandomForestClassifier(
                n_estimators=trial.suggest_int("n_estimators", 120, 320),
                max_depth=trial.suggest_int("max_depth", 4, 14),
                min_samples_leaf=trial.suggest_int("min_samples_leaf", 2, 8),
                random_state=42,
                n_jobs=int(__import__("os").environ.get("MARKET_AI_ML_N_JOBS", "1")),
                class_weight="balanced_subsample",
            )
            model.fit(X_train, y_train)
            pred = model.predict(X_val)
            return f1_score(y_val, pred, average="macro", zero_division=0)

        study.optimize(objective, n_trials=max(int(trial_count), 1))
        params = study.best_params
        models["optuna_random_forest"] = RandomForestClassifier(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            min_samples_leaf=params["min_samples_leaf"],
            random_state=42,
            n_jobs=int(__import__("os").environ.get("MARKET_AI_ML_N_JOBS", "1")),
            class_weight="balanced_subsample",
        )

    best_name = None
    best_model = None
    best_score = -1.0
    leaderboard = []

    for name, model in models.items():
        fitted = model.fit(X_train, y_train)
        pred = fitted.predict(X_val)
        score = float(f1_score(y_val, pred, average="macro", zero_division=0))
        leaderboard.append({"model_name": name, "validation_macro_f1": round(score, 4)})
        if score > best_score:
            best_score = score
            best_name = name
            best_model = fitted

    test_pred = best_model.predict(X_test)
    report = classification_report(y_test, test_pred, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, test_pred, labels=[-1, 0, 1]).tolist()
    test_accuracy = float((test_pred == y_test).mean()) if len(y_test) else 0.0

    feature_importance = {}
    if hasattr(best_model, "feature_importances_"):
        values = list(best_model.feature_importances_)
        feature_importance = {
            FEATURE_COLUMNS[idx]: round(float(values[idx]), 6)
            for idx in range(min(len(FEATURE_COLUMNS), len(values)))
        }
    elif hasattr(best_model, "coef_"):
        coef = np.abs(np.asarray(best_model.coef_)).mean(axis=0)
        feature_importance = {
            FEATURE_COLUMNS[idx]: round(float(coef[idx]), 6)
            for idx in range(min(len(FEATURE_COLUMNS), len(coef)))
        }

    run_id = f"ml-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    run_dir = ML_RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    model_path = run_dir / "model.joblib"
    joblib.dump(
        {
            "model": best_model,
            "feature_columns": FEATURE_COLUMNS,
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "horizon_days": int(horizon_days),
            "buy_threshold": float(buy_threshold),
            "sell_threshold": float(sell_threshold),
        },
        model_path,
    )

    metrics = {
        "validation_leaderboard": leaderboard,
        "best_model_name": best_name,
        "validation_macro_f1": round(best_score, 4),
        "test_accuracy": round(test_accuracy, 4),
        "test_report": report,
        "confusion_matrix": cm,
        "precision_recall_f1_macro": {
            "precision": round(float(report.get("macro avg", {}).get("precision", 0.0)), 4),
            "recall": round(float(report.get("macro avg", {}).get("recall", 0.0)), 4),
            "f1": round(float(report.get("macro avg", {}).get("f1-score", 0.0)), 4),
        },
        "feature_importance": feature_importance,
        "calibration_summary": {
            "enabled": False,
            "note": "Calibration hook is ready for a later pass.",
        },
    }

    with session_scope() as session:
        if set_active:
            session.query(ModelRun).filter(ModelRun.model_type == "ml").update({"is_active": False})
        session.add(ModelRun(
            run_id=run_id,
            model_type="ml",
            model_name=best_name or "unknown",
            status="completed",
            completed_at=datetime.utcnow(),
            artifact_path=str(model_path),
            metrics_json=dumps_json(metrics),
            config_json=dumps_json({
                "symbols": symbols,
                "start_date": start_date,
                "end_date": end_date,
                "horizon_days": horizon_days,
                "buy_threshold": buy_threshold,
                "sell_threshold": sell_threshold,
                "run_optuna": run_optuna and optuna is not None,
                "set_active": bool(set_active),
            }),
            notes="Time-series-safe baseline training run." if set_active else "Time-series-safe baseline training run awaiting promotion review.",
            is_active=bool(set_active),
        ))

    return {
        "run_id": run_id,
        "model_type": "ml",
        "model_name": best_name,
        "artifact_path": str(model_path),
        "metrics": metrics,
        "rows": {"train": int(len(train_df)), "validation": int(len(val_df)), "test": int(len(test_df))},
        "status": "completed",
    }


def set_model_run_active(run_id, active=True):
    with session_scope() as session:
        row = session.query(ModelRun).filter(ModelRun.run_id == run_id).first()
        if row is None:
            return {"error": f"Model run not found: {run_id}"}
        if active:
            session.query(ModelRun).filter(ModelRun.model_type == row.model_type).update({"is_active": False})
        row.is_active = bool(active)
        return {
            "run_id": row.run_id,
            "model_type": row.model_type,
            "is_active": bool(row.is_active),
        }


def list_model_runs(model_type=None):
    with session_scope() as session:
        query = session.query(ModelRun)
        if model_type:
            query = query.filter(ModelRun.model_type == model_type)
        rows = query.order_by(ModelRun.started_at.desc()).limit(50).all()
        return [
            {
                "run_id": row.run_id,
                "model_type": row.model_type,
                "model_name": row.model_name,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "artifact_path": row.artifact_path,
                "is_active": bool(row.is_active),
                "metrics": loads_json(row.metrics_json),
            }
            for row in rows
        ]


def get_model_run(run_id):
    with session_scope() as session:
        row = session.query(ModelRun).filter(ModelRun.run_id == run_id).first()
        if not row:
            return {"error": f"Model run not found: {run_id}"}
        return {
            "run_id": row.run_id,
            "model_type": row.model_type,
            "model_name": row.model_name,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "artifact_path": row.artifact_path,
            "is_active": bool(row.is_active),
            "metrics": loads_json(row.metrics_json),
            "config": loads_json(row.config_json),
            "notes": row.notes,
        }


def infer_latest(symbol="AAPL", start_date="2024-01-01", end_date="2026-04-02", run_id=None):
    if joblib is None:
        return _dependency_error()

    row_data = resolve_model_artifact("ml", run_id=run_id)
    if row_data.get("error"):
        return row_data

    bundle = joblib.load(row_data["artifact_path"])
    raw = _load_local_csv(symbol, start_date, end_date)
    if raw.empty:
        return {"error": f"No local history for {symbol}"}

    features = build_feature_frame(raw, instrument=symbol).dropna(subset=["close"]).copy()
    if features.empty:
        return {"error": f"No inference-ready feature rows for {symbol}"}

    last_row = features.iloc[-1]
    X = pd.DataFrame([{col: float(last_row.get(col, 0.0)) for col in bundle["feature_columns"]}])
    pred_class = int(bundle["model"].predict(X)[0])
    proba = bundle["model"].predict_proba(X)[0]
    class_map = {int(bundle["model"].classes_[idx]): float(proba[idx]) for idx in range(len(proba))}

    result = {
        "symbol": symbol,
        "model_type": "ml",
        "run_id": row_data["run_id"],
        "signal": _prediction_to_signal(pred_class),
        "confidence": round(max(class_map.values()), 4),
        "prob_buy": round(class_map.get(1, 0.0), 4),
        "prob_hold": round(class_map.get(0, 0.0), 4),
        "prob_sell": round(class_map.get(-1, 0.0), 4),
        "as_of": str(last_row["datetime"])[:10],
        "feature_set": "advanced_v1",
        "model_resolution": row_data.get("resolution"),
        "top_features": sorted(
            ((row_data.get("metrics") or {}).get("feature_importance") or {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5],
    }

    persist_feature_snapshot(symbol, {col: float(last_row.get(col, 0.0)) for col in FEATURE_COLUMNS})
    with session_scope() as session:
        session.add(ModelPrediction(
            symbol=symbol,
            model_run_id=row_data["run_id"],
            model_type="ml",
            signal=result["signal"],
            confidence=result["confidence"],
            prob_buy=result["prob_buy"],
            prob_hold=result["prob_hold"],
            prob_sell=result["prob_sell"],
            payload_json=dumps_json(result),
        ))
    return result
