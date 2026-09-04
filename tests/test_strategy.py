"""
tests/test_strategy.py
Automated unit tests for leverage mathematics, session filters, and backtest execution logic.
"""

import unittest
import pandas as pd
from core.leverage_math import (
    get_long_liquidation_price,
    get_short_liquidation_price,
    calc_tp_sl_prices,
    calc_realized_pnl_pct,
)
from core.session_filter import enrich_session_columns, filter_weekdays_only
from engine.backtester import LiquidityHuntBacktester


class TestLeverageStrategy(unittest.TestCase):
    def test_liquidation_math(self):
        entry = 1.48
        # 100x Long with 0.4% MMR: liq price is entry * (1 - 0.01 + 0.004) = 1.48 * 0.994 = 1.47112
        long_liq_100x = get_long_liquidation_price(entry, 100.0, mmr=0.004)
        self.assertAlmostEqual(long_liq_100x, 1.47112, places=4)

        # 100x Short with 0.4% MMR: liq price is entry * (1 + 0.01 - 0.004) = 1.48 * 1.006 = 1.48888
        short_liq_100x = get_short_liquidation_price(entry, 100.0, mmr=0.004)
        self.assertAlmostEqual(short_liq_100x, 1.48888, places=4)

    def test_tp_sl_calculations(self):
        entry = 1.50
        lev = 20.0
        # 25% target ROI at 20x -> 1.25% price distance
        tp_long, sl_long = calc_tp_sl_prices(entry, "long", lev, target_roi_pct=25.0, sl_roi_pct=25.0)
        self.assertAlmostEqual(tp_long, 1.50 * 1.0125, places=5)
        self.assertAlmostEqual(sl_long, 1.50 * 0.9875, places=5)

    def test_realized_pnl_net_fees(self):
        # Long entry at 1.00, TP at 1.0125 (+1.25% price gain at 20x = +25% gross)
        # Maker fee 0.02% in, Maker fee 0.02% out -> 0.04% * 20 = 0.8% fee on margin
        net_roi = calc_realized_pnl_pct(
            entry_price=1.00,
            exit_price=1.0125,
            side="long",
            leverage=20.0,
            maker_fee_pct=0.0002,
            taker_fee_pct=0.0005,
            is_tp=True,
        )
        self.assertAlmostEqual(net_roi, 25.0 - 0.8, places=2)

    def test_session_filtering(self):
        # Create small test series with Monday 00:00 and Sunday 12:00
        df = pd.DataFrame({
            "open_time": pd.to_datetime(["2025-01-06 00:00:00", "2025-01-12 12:00:00"], utc=True),
            "open": [1.0, 1.0],
            "high": [1.1, 1.1],
            "low": [0.9, 0.9],
            "close": [1.0, 1.0],
            "volume": [1000, 1000],
        })
        enriched = enrich_session_columns(df)
        self.assertEqual(enriched.loc[0, "candle_num"], 1)
        self.assertEqual(enriched.loc[0, "is_weekend"], False)
        self.assertEqual(enriched.loc[1, "candle_num"], 4)
        self.assertEqual(enriched.loc[1, "is_weekend"], True)

        weekdays = filter_weekdays_only(enriched)
        self.assertEqual(len(weekdays), 1)


if __name__ == "__main__":
    unittest.main()
