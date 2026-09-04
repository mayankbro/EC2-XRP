"""
engine/backtester.py
Event-driven quantitative backtester simulating 4H leverage-liquidity hunt strategies
with OCO bracket orders, strict 1-trade-per-day rules, weekend filtering, and fee models.
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

from core.leverage_math import calc_tp_sl_prices, calc_realized_pnl_pct
from core.volume_profiler import calculate_hunt_bands, compute_volume_and_volatility_features
from core.session_filter import enrich_session_columns, filter_weekdays_only
from engine.metrics import compute_performance_metrics


class LiquidityHuntBacktester:
    def __init__(
        self,
        leverage: float = 20.0,
        target_roi_pct: float = 25.0,
        sl_roi_pct: float = 25.0,
        base_band_pct: float = 0.015,
        use_volume_scaling: bool = False,
        min_prior_rvol: float = 0.0,
        allowed_candles: Optional[List[int]] = None,
        max_trades_per_day: int = 1,
        no_weekends: bool = True,
        is_dynamic: bool = False,
        maker_fee_pct: float = 0.0002,  # 0.02% VIP 0 maker fee
        taker_fee_pct: float = 0.0005,  # 0.05% VIP 0 taker fee
        slippage_pct: float = 0.0001,   # 0.01% slippage
    ):
        self.leverage = leverage
        self.target_roi_pct = target_roi_pct
        self.sl_roi_pct = sl_roi_pct
        self.base_band_pct = base_band_pct
        self.use_volume_scaling = use_volume_scaling
        self.min_prior_rvol = min_prior_rvol
        self.is_dynamic = is_dynamic
        # Default to Candles 3 & 4 (London/NY overlap) if not specified, or all candles if [1..6]
        self.allowed_candles = allowed_candles if allowed_candles is not None else [3, 4]
        self.max_trades_per_day = max_trades_per_day
        self.no_weekends = no_weekends
        self.maker_fee_pct = maker_fee_pct
        self.taker_fee_pct = taker_fee_pct
        self.slippage_pct = slippage_pct

    def run(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Executes backtest over the provided OHLCV dataset.
        Returns detailed trade records, cumulative series, and performance metrics.
        """
        # Preprocessing & session tagging
        df_proc = enrich_session_columns(df)
        if self.no_weekends:
            df_proc = filter_weekdays_only(df_proc)
        df_proc = compute_volume_and_volatility_features(df_proc)

        trades: List[Dict[str, Any]] = []
        grouped_by_date = df_proc.groupby("date")

        for trade_date, day_df in grouped_by_date:
            trades_today = 0

            for _, row in day_df.iterrows():
                if trades_today >= self.max_trades_per_day:
                    break

                c_num = row["candle_num"]
                if c_num not in self.allowed_candles:
                    continue

                # RVOL filter check
                prior_rvol = row["prior_rvol"]
                if prior_rvol < self.min_prior_rvol:
                    continue

                # Check dynamic parameters if enabled
                if self.is_dynamic:
                    atr = row.get("prior_atr_pct", row.get("prior_atr4_pct", 2.0))
                    if atr > 3.2:
                        continue  # Skip high-volatility breakout danger zone
                    if atr <= 1.8:
                        current_lev = 20.0
                        current_band = 0.015
                        current_margin_weight = 0.15
                        current_tier = "A+"
                    else:
                        current_lev = 15.0
                        current_band = 0.018
                        current_margin_weight = 0.10
                        current_tier = "Standard"
                else:
                    current_lev = self.leverage
                    current_band = self.base_band_pct
                    current_margin_weight = 0.10
                    current_tier = "Static"

                open_p = row["open"]
                high_p = row["high"]
                low_p = row["low"]
                close_p = row["close"]
                open_time = row["open_time"]

                # Calculate hunt limits at candle open
                upper_limit, lower_limit = calculate_hunt_bands(
                    open_price=open_p,
                    base_band_pct=current_band,
                    prior_rvol=prior_rvol,
                    use_volume_scaling=self.use_volume_scaling,
                )

                hit_upper = high_p >= upper_limit
                hit_lower = low_p <= lower_limit

                # Case 1: Neither limit was hit -> orders expire unfilled
                if not hit_upper and not hit_lower:
                    continue

                # Case 2: Both extremes touched in same 4H candle (~4% frequency)
                # Conservative institutional assumption: stop loss hit due to extreme volatility
                if hit_upper and hit_lower:
                    side = "short" if (close_p < open_p) else "long"
                    entry_p = upper_limit if side == "short" else lower_limit
                    net_pnl = -self.sl_roi_pct - ((self.maker_fee_pct + self.taker_fee_pct) * current_lev * 100.0)
                    trades.append({
                        "date": trade_date,
                        "open_time": open_time.strftime("%Y-%m-%d %H:%M"),
                        "candle_num": c_num,
                        "session": row["session_name"],
                        "tier": current_tier,
                        "margin_weight": current_margin_weight,
                        "side": side,
                        "entry_price": round(entry_p, 5),
                        "exit_price": round(entry_p * 1.015 if side == "short" else entry_p * 0.985, 5),
                        "exit_reason": "SL_AMBIGUOUS_DUAL_HIT",
                        "pnl_pct": round(net_pnl, 2),
                        "is_win": False,
                    })
                    trades_today += 1
                    break

                # Case 3: Upper Limit Hit -> Enter Short (fading the short liquidation sweep)
                if hit_upper:
                    entry_p = upper_limit * (1.0 - self.slippage_pct)
                    tp_p, sl_p = calc_tp_sl_prices(
                        entry_price=entry_p,
                        side="short",
                        leverage=current_lev,
                        target_roi_pct=self.target_roi_pct,
                        sl_roi_pct=self.sl_roi_pct,
                    )

                    hit_sl = high_p >= sl_p
                    hit_tp = low_p <= tp_p

                    if hit_sl and not hit_tp:
                        exit_p = sl_p
                        exit_reason = "SL"
                        is_win = False
                    elif hit_tp and not hit_sl:
                        exit_p = tp_p
                        exit_reason = "TP"
                        is_win = True
                    elif hit_sl and hit_tp:
                        # Conservative assumption if both post-entry targets touched
                        exit_p = sl_p
                        exit_reason = "SL"
                        is_win = False
                    else:
                        # Reversion held to candle close
                        exit_p = close_p
                        exit_reason = "TIME_CLOSE"
                        is_win = (entry_p - exit_p) > 0

                    net_pnl = calc_realized_pnl_pct(
                        entry_price=entry_p,
                        exit_price=exit_p,
                        side="short",
                        leverage=current_lev,
                        maker_fee_pct=self.maker_fee_pct,
                        taker_fee_pct=self.taker_fee_pct,
                        is_tp=(exit_reason == "TP"),
                    )

                    trades.append({
                        "date": trade_date,
                        "open_time": open_time.strftime("%Y-%m-%d %H:%M"),
                        "candle_num": c_num,
                        "session": row["session_name"],
                        "tier": current_tier,
                        "margin_weight": current_margin_weight,
                        "side": "short",
                        "entry_price": round(entry_p, 5),
                        "exit_price": round(exit_p, 5),
                        "exit_reason": exit_reason,
                        "pnl_pct": round(net_pnl, 2),
                        "is_win": is_win,
                    })
                    trades_today += 1
                    break

                # Case 4: Lower Limit Hit -> Enter Long (fading the long liquidation sweep)
                if hit_lower:
                    entry_p = lower_limit * (1.0 + self.slippage_pct)
                    tp_p, sl_p = calc_tp_sl_prices(
                        entry_price=entry_p,
                        side="long",
                        leverage=current_lev,
                        target_roi_pct=self.target_roi_pct,
                        sl_roi_pct=self.sl_roi_pct,
                    )

                    hit_sl = low_p <= sl_p
                    hit_tp = high_p >= tp_p

                    if hit_sl and not hit_tp:
                        exit_p = sl_p
                        exit_reason = "SL"
                        is_win = False
                    elif hit_tp and not hit_sl:
                        exit_p = tp_p
                        exit_reason = "TP"
                        is_win = True
                    elif hit_sl and hit_tp:
                        exit_p = sl_p
                        exit_reason = "SL"
                        is_win = False
                    else:
                        exit_p = close_p
                        exit_reason = "TIME_CLOSE"
                        is_win = (exit_p - entry_p) > 0

                    net_pnl = calc_realized_pnl_pct(
                        entry_price=entry_p,
                        exit_price=exit_p,
                        side="long",
                        leverage=current_lev,
                        maker_fee_pct=self.maker_fee_pct,
                        taker_fee_pct=self.taker_fee_pct,
                        is_tp=(exit_reason == "TP"),
                    )

                    trades.append({
                        "date": trade_date,
                        "open_time": open_time.strftime("%Y-%m-%d %H:%M"),
                        "candle_num": c_num,
                        "session": row["session_name"],
                        "tier": current_tier,
                        "margin_weight": current_margin_weight,
                        "side": "long",
                        "entry_price": round(entry_p, 5),
                        "exit_price": round(exit_p, 5),
                        "exit_reason": exit_reason,
                        "pnl_pct": round(net_pnl, 2),
                        "is_win": is_win,
                    })
                    trades_today += 1
                    break

        metrics = compute_performance_metrics(trades)
        return {
            "parameters": {
                "leverage": self.leverage,
                "target_roi_pct": self.target_roi_pct,
                "sl_roi_pct": self.sl_roi_pct,
                "base_band_pct": self.base_band_pct,
                "allowed_candles": self.allowed_candles,
                "use_volume_scaling": self.use_volume_scaling,
                "no_weekends": self.no_weekends,
            },
            "metrics": metrics,
            "trades": trades,
        }
