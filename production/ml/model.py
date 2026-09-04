"""
production/ml/model.py
Machine Learning Classifier for Real-Time Liquidity Sweep Validation.
Predicts probability of successful mean-reversion P(Reversion) using
rolling market microstructure features.
"""

import os
import joblib
import logging
import numpy as np

logger = logging.getLogger("MLModel")


class LiquidityReversionClassifier:
    def __init__(self, weights_path: str = "production/ml/model_weights.pkl"):
        self.weights_path = weights_path
        self.model = None
        self.load_model()

    def load_model(self) -> bool:
        """Loads pre-trained model weights from disk if available."""
        if os.path.exists(self.weights_path):
            try:
                self.model = joblib.load(self.weights_path)
                logger.info(f"Loaded ML model weights from {self.weights_path}")
                return True
            except Exception as e:
                logger.warning(f"Could not load ML weights: {e}")
        return False

    def predict_reversion_probability(self, features: dict) -> float:
        """
        Predicts P(Reversion) ∈ [0.0, 1.0].
        Features expected: atr_pct, rvol, upper_wick_ratio, lower_wick_ratio, hour, day_of_week
        """
        # If model is trained and loaded, run inference
        if self.model is not None:
            try:
                import pandas as pd
                df_vec = pd.DataFrame([{
                    "atr_pct": features.get("atr_pct", 2.0),
                    "rvol": features.get("rvol", 1.0),
                    "upper_wick_ratio": features.get("upper_wick_ratio", 0.2),
                    "lower_wick_ratio": features.get("lower_wick_ratio", 0.2),
                    "hour": features.get("hour", 12),
                    "day_of_week": features.get("day_of_week", 2),
                }])
                prob = float(self.model.predict_proba(df_vec)[0][1])
                return round(prob, 3)
            except Exception as e:
                logger.error(f"Inference error: {e}")

        # Robust quantitative fallback heuristic (based on 6.66-year backtest weights)
        base_prob = 0.67
        atr = features.get("atr_pct", 2.0)
        rvol = features.get("rvol", 1.0)

        # Volatility bonus/penalty
        if atr <= 1.8:
            base_prob += 0.08  # Low ATR increases reversion probability to ~75%
        elif atr > 3.2:
            base_prob -= 0.24  # High ATR drops reversion probability to ~43%

        # RVOL bonus
        if 0.8 <= rvol <= 1.5:
            base_prob += 0.03

        return round(float(np.clip(base_prob, 0.1, 0.95)), 3)
