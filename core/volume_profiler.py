"""
core/volume_profiler.py
Calculates rolling volume indicators, RVOL (Relative Volume), ATR,
and dynamic volatility-scaled liquidity hunt levels without lookahead bias.
"""

import numpy as np
import pandas as pd


def compute_volume_and_volatility_features(
    df: pd.DataFrame,
    vol_lookback: int = 4,
    atr_lookback: int = 4,
) -> pd.DataFrame:
    """
    Enriches OHLCV dataframe with prior rolling volume and volatility features.
    Crucially uses `.shift(1)` to ensure features at candle open are computed
    using ONLY strictly prior historical candles (zero lookahead).
    """
    df = df.copy()

    # Prior rolling average volume of last N candles
    df["prior_vol_sma"] = df["volume"].rolling(vol_lookback).mean().shift(1)
    
    # RVOL of the prior candle relative to its preceding baseline
    df["prior_rvol"] = (df["volume"].shift(1) / df["prior_vol_sma"]).fillna(1.0)

    # True Range
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))

    # Prior ATR of last N candles
    df["prior_atr"] = df["tr"].rolling(atr_lookback).mean().shift(1)
    df["prior_atr_pct"] = (df["prior_atr"] / df["open"] * 100.0).fillna(2.0)

    # Upper and Lower Wick metrics of previous candle
    prev_high = df["high"].shift(1)
    prev_low = df["low"].shift(1)
    prev_open = df["open"].shift(1)
    prev_close = df["close"].shift(1)
    prev_range = np.maximum(prev_high - prev_low, 1e-6)

    prev_upper_wick = prev_high - np.maximum(prev_open, prev_close)
    prev_lower_wick = np.minimum(prev_open, prev_close) - prev_low

    df["prior_upper_wick_ratio"] = (prev_upper_wick / prev_range).fillna(0.0)
    df["prior_lower_wick_ratio"] = (prev_lower_wick / prev_range).fillna(0.0)

    return df


def calculate_hunt_bands(
    open_price: float,
    base_band_pct: float = 0.015,
    prior_rvol: float = 1.0,
    use_volume_scaling: bool = False,
) -> tuple[float, float]:
    """
    Computes upper (short limit) and lower (long limit) order price levels.
    
    If use_volume_scaling is True:
    Scales the band distance by sqrt(prior_rvol) so that when recent volume
    has been exceptionally quiet, bands tighten; when explosive, bands widen.
    """
    effective_band = base_band_pct
    if use_volume_scaling:
        scale_factor = np.clip(np.sqrt(prior_rvol), 0.75, 1.5)
        effective_band = base_band_pct * scale_factor

    upper_limit = open_price * (1.0 + effective_band)
    lower_limit = open_price * (1.0 - effective_band)
    return upper_limit, lower_limit
