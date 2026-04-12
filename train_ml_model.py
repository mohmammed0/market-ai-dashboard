from pathlib import Path
import json
import joblib
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

DATA_FILE = Path("ml_training_data.csv")
ARTIFACT_DIR = Path("model_artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)

MODEL_FILE = ARTIFACT_DIR / "rf_signal_model.joblib"
META_FILE = ARTIFACT_DIR / "rf_signal_model_meta.json"

df = pd.read_csv(DATA_FILE)
df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)

feature_cols = [
    "open", "high", "low", "close", "volume",
    "ma20", "ma50", "ema20", "ema50",
    "rsi14", "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_lower", "bb_width",
    "atr14", "volume_ratio",
    "stoch_k", "stoch_d",
    "plus_di14", "minus_di14", "adx14",
    "volatility20", "breakout_high_20", "breakout_low_20",
    "technical_score"
]

X_num = df[feature_cols].copy()
X_cat = pd.get_dummies(df["instrument"], prefix="instrument")
X = pd.concat([X_num, X_cat], axis=1)
y = df["target_class"].astype(int)

split_idx = int(len(df) * 0.8)
X_train = X.iloc[:split_idx].copy()
X_test = X.iloc[split_idx:].copy()
y_train = y.iloc[:split_idx].copy()
y_test = y.iloc[split_idx:].copy()

model = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    min_samples_leaf=5,
    random_state=42,
    n_jobs=-1,
    class_weight="balanced_subsample"
)

model.fit(X_train, y_train)
pred = model.predict(X_test)

accuracy = accuracy_score(y_test, pred)
report = classification_report(y_test, pred, output_dict=True, zero_division=0)
cm = confusion_matrix(y_test, pred, labels=[-1, 0, 1]).tolist()

joblib.dump(
    {
        "model": model,
        "feature_columns": list(X.columns),
        "base_feature_columns": feature_cols,
    },
    MODEL_FILE
)

meta = {
    "rows_total": int(len(df)),
    "rows_train": int(len(X_train)),
    "rows_test": int(len(X_test)),
    "features_total": int(len(X.columns)),
    "accuracy": float(accuracy),
    "labels_order": [-1, 0, 1],
    "confusion_matrix": cm,
    "classification_report": report,
}
META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")

print("MODEL_TRAINED")
print("accuracy=", round(accuracy, 4))
print("train_rows=", len(X_train))
print("test_rows=", len(X_test))
print("features_total=", len(X.columns))
print("model_file=", MODEL_FILE)
print("meta_file=", META_FILE)
print("confusion_matrix=")
print(cm)
