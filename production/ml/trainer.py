import datetime
import os
import sys
import joblib
import numpy as np
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report
from sklearn.model_selection import train_test_split

from data.fetcher import load_dataset
from engine.backtester import LiquidityHuntBacktester

MODEL_OUTPUT_PATH = "production/ml/model_weights.pkl"


def build_training_dataset_from_history() -> pd.DataFrame:
    """Simulates trades across historical dataset to generate labelled samples."""
    df = load_dataset()
    bt = LiquidityHuntBacktester(
        leverage=15.0,
        target_roi_pct=25.0,
        sl_roi_pct=25.0,
        base_band_pct=0.018,
        allowed_candles=[1, 2, 3, 4, 5, 6],
        no_weekends=True,
    )
    res = bt.run(df)
    trades = res["trades"]

    # Merge features
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["hour"] = df["open_time"].dt.hour
    df["day_of_week"] = df["open_time"].dt.dayofweek
    df["prior_vol_sma4"] = df["volume"].rolling(4).mean().shift(1)
    df["prior_rvol"] = (df["volume"].shift(1) / df["prior_vol_sma4"]).fillna(1.0)
    df["tr"] = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    df["prior_atr4_pct"] = (df["tr"].rolling(4).mean().shift(1) / df["open"] * 100).fillna(2.0)

    # Wick ratios
    p_range = np.maximum(df["high"].shift(1) - df["low"].shift(1), 1e-6)
    p_upper = df["high"].shift(1) - np.maximum(df["open"].shift(1), df["close"].shift(1))
    p_lower = np.minimum(df["open"].shift(1), df["close"].shift(1)) - df["low"].shift(1)
    df["upper_wick_ratio"] = (p_upper / p_range).fillna(0.2)
    df["lower_wick_ratio"] = (p_lower / p_range).fillna(0.2)

    df_map = df.set_index("open_time")
    records = []
    for t in trades:
        ts = pd.to_datetime(t["open_time"], utc=True)
        if ts in df_map.index:
            r = df_map.loc[ts]
            records.append({
                "atr_pct": r["prior_atr4_pct"],
                "rvol": r["prior_rvol"],
                "upper_wick_ratio": r["upper_wick_ratio"],
                "lower_wick_ratio": r["lower_wick_ratio"],
                "hour": r["hour"],
                "day_of_week": r["day_of_week"],
                "target": 1 if t["is_win"] else 0,
            })

    return pd.DataFrame(records)


def train_and_save_model(output_path: str = MODEL_OUTPUT_PATH):
    """Trains the model and saves serialized weights."""
    print("Building training dataset from historical trade executions...")
    data = build_training_dataset_from_history()
    print(f"Generated {len(data)} labelled trade samples.")

    feature_cols = ["atr_pct", "rvol", "upper_wick_ratio", "lower_wick_ratio", "hour", "day_of_week"]
    X = data[feature_cols]
    y = data["target"]

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.20, shuffle=False)

    print("Training Calibrated Gradient Boosting Model...")
    model = GradientBoostingClassifier(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=3,
        subsample=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # Validation
    y_pred = model.predict(X_val)
    y_prob = model.predict_proba(X_val)[:, 1]
    acc = accuracy_score(y_val, y_pred)
    auc = roc_auc_score(y_val, y_prob)

    print(f"\nModel Training Completed:")
    print(f"  Validation Accuracy: {acc*100:.2f}%")
    print(f"  ROC-AUC Score:       {auc:.3f}")
    print("\nClassification Report:\n", classification_report(y_val, y_pred))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    joblib.dump(model, output_path)
    print(f"Model weights saved to {output_path}")


if __name__ == "__main__":
    train_and_save_model()
