from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from backend.app.config import ROOT_DIR
from backend.app.models import ModelPrediction, ModelRun
from backend.app.services.features import FEATURE_COLUMNS, build_feature_frame, create_target_labels
from backend.app.services.market_data import DEFAULT_SYMBOLS, _load_local_csv
from backend.app.services.model_artifact_runtime import resolve_model_artifact
from backend.app.services.storage import dumps_json, session_scope

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
except Exception:  # pragma: no cover - optional dependency
    torch = None
    nn = None
    DataLoader = None
    TensorDataset = None


ARTIFACT_ROOT = ROOT_DIR / "model_artifacts"
DL_RUN_ROOT = ARTIFACT_ROOT / "dl_runs"
DL_RUN_ROOT.mkdir(parents=True, exist_ok=True)


if nn is not None:
    class GRUClassifier(nn.Module):
        def __init__(self, input_size, hidden_size=48, num_layers=1, num_classes=3):
            super().__init__()
            self.gru = nn.GRU(input_size, hidden_size, num_layers=num_layers, batch_first=True)
            self.head = nn.Linear(hidden_size, num_classes)

        def forward(self, x):
            out, _ = self.gru(x)
            return self.head(out[:, -1, :])
else:
    GRUClassifier = None


def _dependency_error():
    return {"error": "Missing DL dependencies: torch"}


def _build_sequence_frame(symbols, start_date, end_date, horizon_days, buy_threshold, sell_threshold):
    parts = []
    for symbol in symbols:
        raw = _load_local_csv(symbol, start_date, end_date)
        if raw.empty:
            continue
        features = build_feature_frame(raw, instrument=symbol)
        dataset = create_target_labels(features, horizon_days=horizon_days, buy_threshold=buy_threshold, sell_threshold=sell_threshold)
        dataset["instrument"] = symbol
        dataset = dataset.dropna(subset=["future_close"]).copy()
        if not dataset.empty:
            parts.append(dataset)
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    return df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)


def _make_sequences(df, sequence_length):
    X, y = [], []
    for _, part in df.groupby("instrument"):
        part = part.sort_values("datetime").reset_index(drop=True)
        values = part[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        targets = part["target_class"].map({-1: 0, 0: 1, 1: 2}).to_numpy(dtype=np.int64)
        for idx in range(sequence_length, len(part)):
            X.append(values[idx - sequence_length:idx])
            y.append(targets[idx])
    if not X:
        return np.empty((0, sequence_length, len(FEATURE_COLUMNS))), np.empty((0,))
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int64)


def train_sequence_model(
    symbols=None,
    start_date="2020-01-01",
    end_date="2026-04-02",
    sequence_length=20,
    horizon_days=5,
    buy_threshold=0.02,
    sell_threshold=-0.02,
    epochs=8,
    hidden_size=48,
    learning_rate=1e-3,
    set_active=True,
):
    if torch is None:
        return _dependency_error()

    symbols = [str(symbol).upper().strip() for symbol in (symbols or DEFAULT_SYMBOLS) if str(symbol).strip()]
    df = _build_sequence_frame(symbols, start_date, end_date, horizon_days, buy_threshold, sell_threshold)
    if df.empty:
        return {"error": "No sequence training rows available from current local data."}

    X, y = _make_sequences(df, int(sequence_length))
    if len(X) < 30:
        return {"error": "Not enough sequence samples for DL training."}

    train_end = max(int(len(X) * 0.7), 1)
    val_end = max(int(len(X) * 0.85), train_end + 1)
    X_train, y_train = X[:train_end], y[:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]
    X_test, y_test = X[val_end:], y[val_end:]

    model = GRUClassifier(input_size=len(FEATURE_COLUMNS), hidden_size=int(hidden_size))
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))
    criterion = nn.CrossEntropyLoss()
    train_loader = DataLoader(TensorDataset(torch.tensor(X_train), torch.tensor(y_train)), batch_size=32, shuffle=False)
    val_inputs = torch.tensor(X_val)
    val_targets = torch.tensor(y_val)

    best_loss = float("inf")
    patience = 3
    patience_left = patience
    history = []

    run_id = f"dl-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    run_dir = DL_RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "best_model.pt"

    for epoch in range(max(int(epochs), 1)):
        model.train()
        running_loss = 0.0
        for batch_inputs, batch_targets in train_loader:
            optimizer.zero_grad()
            loss = criterion(model(batch_inputs), batch_targets)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item())

        model.eval()
        with torch.no_grad():
            val_logits = model(val_inputs)
            val_loss = float(criterion(val_logits, val_targets).item())
            val_pred = torch.argmax(val_logits, dim=1)
            val_acc = float((val_pred == val_targets).float().mean().item())

        history.append({
            "epoch": epoch + 1,
            "train_loss": round(running_loss / max(len(train_loader), 1), 6),
            "val_loss": round(val_loss, 6),
            "val_accuracy": round(val_acc, 6),
        })

        if val_loss < best_loss:
            best_loss = val_loss
            patience_left = patience
            torch.save({
                "state_dict": model.state_dict(),
                "feature_columns": FEATURE_COLUMNS,
                "sequence_length": int(sequence_length),
                "hidden_size": int(hidden_size),
            }, checkpoint_path)
        else:
            patience_left -= 1
            if patience_left <= 0:
                break

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    with torch.no_grad():
        test_inputs = torch.tensor(X_test)
        test_targets = torch.tensor(y_test)
        test_logits = model(test_inputs)
        test_pred = torch.argmax(test_logits, dim=1)
        test_acc = float((test_pred == test_targets).float().mean().item()) if len(X_test) else 0.0

    metrics = {
        "validation_history": history,
        "test_accuracy": round(test_acc, 4),
        "sequence_length": int(sequence_length),
        "best_checkpoint_path": str(checkpoint_path),
        "classes": ["SELL", "HOLD", "BUY"],
    }

    with session_scope() as session:
        if set_active:
            session.query(ModelRun).filter(ModelRun.model_type == "dl").update({"is_active": False})
        session.add(ModelRun(
            run_id=run_id,
            model_type="dl",
            model_name="gru_sequence",
            status="completed",
            completed_at=datetime.utcnow(),
            artifact_path=str(checkpoint_path),
            metrics_json=dumps_json(metrics),
            config_json=dumps_json({
                "symbols": symbols,
                "start_date": start_date,
                "end_date": end_date,
                "sequence_length": sequence_length,
                "epochs": epochs,
                "hidden_size": hidden_size,
                "learning_rate": learning_rate,
                "set_active": bool(set_active),
            }),
            notes="Sequence-model GRU training run." if set_active else "Sequence-model GRU training run awaiting promotion review.",
            is_active=bool(set_active),
        ))

    return {
        "run_id": run_id,
        "model_type": "dl",
        "model_name": "gru_sequence",
        "artifact_path": str(checkpoint_path),
        "metrics": metrics,
        "rows": {"train": int(len(X_train)), "validation": int(len(X_val)), "test": int(len(X_test))},
        "status": "completed",
    }


def infer_sequence(symbol="AAPL", start_date="2024-01-01", end_date="2026-04-02", run_id=None):
    if torch is None:
        return _dependency_error()

    row_data = resolve_model_artifact("dl", run_id=run_id)
    if row_data.get("error"):
        return row_data

    checkpoint = torch.load(row_data["artifact_path"], map_location="cpu")
    raw = _load_local_csv(symbol, start_date, end_date)
    if raw.empty:
        return {"error": f"No local history for {symbol}"}

    features = build_feature_frame(raw, instrument=symbol)
    seq_len = int(checkpoint.get("sequence_length", 20))
    if len(features) <= seq_len:
        return {"error": f"Not enough feature rows for {symbol} sequence inference."}

    last_seq = features[FEATURE_COLUMNS].tail(seq_len).to_numpy(dtype=np.float32)
    model = GRUClassifier(input_size=len(FEATURE_COLUMNS), hidden_size=int(checkpoint.get("hidden_size", 48)))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor(last_seq).unsqueeze(0))
        probs = torch.softmax(logits, dim=1).cpu().numpy()[0]

    result = {
        "symbol": symbol,
        "model_type": "dl",
        "run_id": row_data["run_id"],
        "signal": ["SELL", "HOLD", "BUY"][int(np.argmax(probs))],
        "confidence": round(float(np.max(probs)), 4),
        "prob_sell": round(float(probs[0]), 4),
        "prob_hold": round(float(probs[1]), 4),
        "prob_buy": round(float(probs[2]), 4),
        "as_of": str(features.iloc[-1]["datetime"])[:10],
        "sequence_length": seq_len,
        "model_resolution": row_data.get("resolution"),
    }

    with session_scope() as session:
        session.add(ModelPrediction(
            symbol=symbol,
            model_run_id=row_data["run_id"],
            model_type="dl",
            signal=result["signal"],
            confidence=result["confidence"],
            prob_buy=result["prob_buy"],
            prob_hold=result["prob_hold"],
            prob_sell=result["prob_sell"],
            payload_json=dumps_json(result),
        ))
    return result
