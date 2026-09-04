"""
tests/test_production.py
Automated unit tests for production modules:
MockBroker, OrderManager, RiskCircuitBreaker, FeaturePipeline, and ML Model.
"""

import asyncio
import datetime
import unittest
from production.execution.mock_broker import MockBroker
from production.execution.order_manager import OrderManager, OrderState
from production.risk.circuit_breakers import RiskCircuitBreaker
from production.data_feed.feature_pipeline import LiveFeaturePipeline
from production.ml.model import LiquidityReversionClassifier


class TestProductionComponents(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_mock_broker_and_order_manager(self):
        broker = MockBroker(initial_capital_inr=10000.0)
        mgr = OrderManager(broker_client=broker, pair="B-XRP_USDT")

        # 1. Place dual bracket
        self.loop.run_until_complete(
            mgr.place_dual_bracket(
                upper_limit=1.52,
                lower_limit=1.46,
                leverage=15.0,
                margin_inr=1000.0,
                tier="Standard",
            )
        )
        self.assertEqual(mgr.state, OrderState.BRACKET_ACTIVE)
        self.assertIsNotNone(mgr.upper_order_id)
        self.assertIsNotNone(mgr.lower_order_id)

        # 2. Simulate price tick that fills Lower Limit (Long entry)
        fill_events = broker.update_price_and_check_fills(1.455)
        self.assertEqual(len(fill_events), 1)
        self.assertEqual(fill_events[0]["order"]["side"], "buy")

        # 3. Handle fill event (OCO: upper order canceled)
        self.loop.run_until_complete(
            mgr.handle_fill_event(fill_events[0]["order"], target_roi_pct=25.0, sl_roi_pct=25.0)
        )
        self.assertEqual(mgr.state, OrderState.IN_POSITION)
        self.assertEqual(mgr.active_position.side, "long")
        self.assertIsNone(mgr.upper_order_id)  # Canceled

        # 4. Check TP exit
        tp_price = mgr.active_position.tp_price
        exit_result = self.loop.run_until_complete(mgr.check_position_exit(tp_price + 0.01))
        self.assertIsNotNone(exit_result)
        self.assertEqual(exit_result["exit_reason"], "TP")
        self.assertGreater(exit_result["pnl_inr"], 0.0)
        self.assertGreater(broker.capital_inr, 10000.0)

    def test_risk_circuit_breakers(self):
        risk = RiskCircuitBreaker(max_trades_per_day=1, max_daily_losses=2)
        # Tuesday 12:00 UTC
        weekday_dt = datetime.datetime(2026, 9, 1, 12, 0, tzinfo=datetime.timezone.utc)
        can_trade, _ = risk.can_open_new_trade(weekday_dt)
        self.assertTrue(can_trade)

        # Record 1 trade completed -> should block next trade on same day
        risk.record_trade_completion(is_win=True)
        can_trade_again, reason = risk.can_open_new_trade(weekday_dt)
        self.assertFalse(can_trade_again)
        self.assertIn("Daily trade quota reached", reason)

        # Saturday check -> should block
        saturday_dt = datetime.datetime(2026, 9, 5, 12, 0, tzinfo=datetime.timezone.utc)
        can_trade_weekend, reason_weekend = risk.can_open_new_trade(saturday_dt)
        self.assertFalse(can_trade_weekend)
        self.assertIn("Weekend", reason_weekend)

    def test_ml_reversion_classifier(self):
        clf = LiquidityReversionClassifier("production/ml/model_weights.pkl")
        self.assertIsNotNone(clf.model)

        # A+ low-volatility features
        prob_a_plus = clf.predict_reversion_probability({
            "atr_pct": 1.2,
            "rvol": 1.0,
            "upper_wick_ratio": 0.3,
            "lower_wick_ratio": 0.3,
            "hour": 12,
            "day_of_week": 2,
        })
        self.assertGreater(prob_a_plus, 0.60)


if __name__ == "__main__":
    unittest.main()
