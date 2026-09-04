"""
production/data_feed/feature_pipeline.py
Real-time streaming feature pipeline for live trade decision making.
Maintains rolling window of historical klines and computes ATR, RVOL,
and setup quality tiers without lookahead bias.
"""

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass
class SetupMetrics:
    tier: str                  # "A+", "Standard", or "HighRisk"
    leverage: float            # e.g. 20.0 or 15.0
    sweep_band_pct: float      # e.g. 0.015 or 0.018
    margin_weight: float       # e.g. 0.15 or 0.10
    atr_pct: float             # 4-candle ATR as % of open
    rvol: float                # Relative volume of prior candle
    upper_wick_ratio: float
    lower_wick_ratio: float
    is_tradable: bool          # False if ATR > 3.2% (Danger zone)
    upper_limit: float         # Limit Short entry price
    lower_limit: float         # Limit Long entry price


class LiveFeaturePipeline:
    def __init__(self, history_size: int = 20):
        self.history = deque(maxlen=history_size)
        self.recent_liquidations = deque(maxlen=100)

    def initialize_from_dataframe(self, df):
        """Pre-seeds the rolling buffer with the latest completed candles."""
        for _, row in df.tail(10).iterrows():
            self.history.append({
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })

    def add_completed_kline(self, kline: dict):
        """Appends a newly closed 4H candle to rolling buffer."""
        self.history.append({
            "open": kline["open"],
            "high": kline["high"],
            "low": kline["low"],
            "close": kline["close"],
            "volume": kline["volume"],
        })

    def add_liquidation_event(self, liq: dict):
        """Records a live forced liquidation event from Binance."""
        self.recent_liquidations.append(liq)

    def compute_setup_for_new_candle(self, open_price: float) -> Optional[SetupMetrics]:
        """
        Computes dynamic leverage, sweep bands, and setup quality tier
        at the exact moment a new 4H candle opens (t=0).
        """
        if len(self.history) < 4:
            return None

        # Last 4 completed candles
        recent = list(self.history)[-4:]

        # 1. True Range calculation
        trs = []
        for i in range(1, len(recent)):
            c = recent[i]
            p_close = recent[i - 1]["close"]
            tr = max(
                c["high"] - c["low"],
                abs(c["high"] - p_close),
                abs(c["low"] - p_close),
            )
            trs.append(tr)
        
        atr = np.mean(trs) if trs else (recent[-1]["high"] - recent[-1]["low"])
        atr_pct = (atr / open_price) * 100.0

        # 2. RVOL calculation
        vols = [c["volume"] for c in recent]
        vol_sma4 = np.mean(vols)
        last_vol = recent[-1]["volume"]
        rvol = (last_vol / vol_sma4) if vol_sma4 > 0 else 1.0

        # 3. Prior candle wick ratios
        prev = recent[-1]
        prev_range = max(prev["high"] - prev["low"], 1e-6)
        upper_wick = prev["high"] - max(prev["open"], prev["close"])
        lower_wick = min(prev["open"], prev["close"]) - prev["low"]
        upper_wick_ratio = upper_wick / prev_range
        lower_wick_ratio = lower_wick / prev_range

        # 4. Classification & Dynamic Sizing
        if atr_pct > 3.2:
            # Danger Zone: High breakout risk, skip trading
            tier = "HighRisk"
            is_tradable = False
            leverage = 10.0
            sweep_band_pct = 0.025
            margin_weight = 0.0
        elif atr_pct <= 1.8 and rvol <= 1.8:
            # A+ Coiled Setup: Compressed volatility, clean sweeps
            tier = "A+"
            is_tradable = True
            leverage = 20.0
            sweep_band_pct = 0.015
            margin_weight = 0.15
        else:
            # Standard Setup
            tier = "Standard"
            is_tradable = True
            leverage = 15.0
            sweep_band_pct = 0.018
            margin_weight = 0.10

        upper_limit = open_price * (1.0 + sweep_band_pct)
        lower_limit = open_price * (1.0 - sweep_band_pct)

        return SetupMetrics(
            tier=tier,
            leverage=leverage,
            sweep_band_pct=sweep_band_pct,
            margin_weight=margin_weight,
            atr_pct=round(atr_pct, 2),
            rvol=round(rvol, 2),
            upper_wick_ratio=round(upper_wick_ratio, 2),
            lower_wick_ratio=round(lower_wick_ratio, 2),
            is_tradable=is_tradable,
            upper_limit=round(upper_limit, 5),
            lower_limit=round(lower_limit, 5),
        )
