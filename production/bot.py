"""
production/bot.py
Autonomous 24/7 Production Trading Daemon.
Connects Binance real-time intelligence stream, ML inference engine,
risk circuit breakers, CoinDCX execution engine, and Telegram telemetry.
"""

import asyncio
import datetime
import logging
import os
import signal
import sys

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from production.config import CONFIG
from production.data_feed.binance_ws import BinanceFuturesStream
from production.data_feed.feature_pipeline import LiveFeaturePipeline
from production.execution.coindcx_client import CoinDCXClient
from production.execution.mock_broker import MockBroker
from production.execution.order_manager import OrderManager, OrderState
from production.ml.feature_store import FeatureStore
from production.ml.model import LiquidityReversionClassifier
from production.notifications.telegram_bot import TelegramNotifier
from production.risk.circuit_breakers import RiskCircuitBreaker
from data.fetcher import load_dataset

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("trading_bot.log"),
    ],
)
logger = logging.getLogger("TradingDaemon")


class TradingDaemon:
    def __init__(self):
        self.config = CONFIG
        self.is_running = False

        # 1. Database & State Store
        self.feature_store = FeatureStore(self.config.DATABASE_PATH)

        # 2. Machine Learning Model
        self.ml_model = LiquidityReversionClassifier(self.config.MODEL_WEIGHTS_PATH)

        # 3. Feature Pipeline
        self.feature_pipeline = LiveFeaturePipeline()

        # 4. Risk Circuit Breaker
        self.risk_manager = RiskCircuitBreaker(
            max_trades_per_day=self.config.MAX_TRADES_PER_DAY,
            max_daily_losses=self.config.MAX_CONSECUTIVE_LOSSES,
            max_portfolio_drawdown_pct=self.config.MAX_DRAWDOWN_LOCK_PCT,
            no_weekends=True,
        )

        # 5. Telegram Notifier
        self.notifier = TelegramNotifier(
            bot_token=self.config.TELEGRAM_BOT_TOKEN,
            chat_id=self.config.TELEGRAM_CHAT_ID,
        )

        # 6. Broker & Execution Engine
        if self.config.EXECUTION_MODE == "LIVE":
            logger.info("Initializing LIVE CoinDCX Client...")
            self.broker = CoinDCXClient(
                api_key=self.config.COINDCX_API_KEY,
                api_secret=self.config.COINDCX_API_SECRET,
                base_url=self.config.COINDCX_REST_BASE,
            )
        else:
            logger.info("Initializing MOCK Paper Trading Broker...")
            self.broker = MockBroker(initial_capital_inr=self.config.INITIAL_CAPITAL_INR)

        # 7. Order Manager
        self.order_manager = OrderManager(
            broker_client=self.broker,
            pair=self.config.COINDCX_SYMBOL,
        )

        # 8. Binance WebSocket Stream
        self.stream = BinanceFuturesStream(
            symbol=self.config.BINANCE_SYMBOL,
            on_kline=self.handle_kline_event,
            on_liquidation=self.handle_liquidation_event,
            on_ticker=self.handle_ticker_event,
        )

        self.current_price: float = 0.0
        self.last_candle_start: int = 0

    async def initialize(self):
        """Pre-seeds historical klines and checks initial balances."""
        logger.info("Loading recent historical data to pre-seed rolling feature pipeline...")
        df_hist = load_dataset()
        self.feature_pipeline.initialize_from_dataframe(df_hist)

        balances = await self.broker.get_wallet_balances()
        logger.info(f"Connected to Broker. Wallet status: {balances}")

        await self.notifier.send_message(
            f"🚀 *TRADING BOT INITIALIZED*\n"
            f"• Mode: `{self.config.EXECUTION_MODE}`\n"
            f"• Asset: `{self.config.BINANCE_SYMBOL}` -> `{self.config.COINDCX_SYMBOL}`\n"
            f"• Initial Capital: `₹{self.config.INITIAL_CAPITAL_INR:,.2f}`\n"
            f"• Strategy: Dynamic Adaptive 4H Liquidity Hunt"
        )

    async def start(self):
        """Starts background workers and WebSocket stream."""
        self.is_running = True
        await self.initialize()

        # Launch background tasks
        asyncio.create_task(self.stream.start())
        asyncio.create_task(self._heartbeat_loop())
        logger.info("Trading Daemon running. Listening for Binance market events...")

        while self.is_running:
            await asyncio.sleep(1)

    async def stop(self):
        """Gracefully shuts down the daemon."""
        logger.info("Shutting down Trading Daemon...")
        self.is_running = False
        await self.stream.stop()
        if hasattr(self.broker, "close"):
            await self.broker.close()
        logger.info("Trading Daemon shutdown complete.")

    async def handle_kline_event(self, kline: dict):
        """Handles incoming 4H kline events."""
        self.current_price = kline["close"]
        candle_start = kline["start_time"]
        is_closed = kline["is_closed"]

        # Check if a NEW 4H candle just opened
        if candle_start != self.last_candle_start:
            self.last_candle_start = candle_start
            open_price = kline["open"]
            now_dt = datetime.datetime.now(datetime.timezone.utc)

            logger.info(f"New 4H Candle Opened at {now_dt.strftime('%H:%M UTC')} | Open Price: ${open_price:.4f}")

            # Cancel any expired bracket orders from previous 4H window
            if self.order_manager.state == OrderState.BRACKET_ACTIVE:
                await self.order_manager.cancel_active_brackets()

            # Evaluate Risk Circuit Breakers
            can_trade, reason = self.risk_manager.can_open_new_trade(now_dt)
            if not can_trade:
                logger.info(f"Trade blocked by Risk Manager: {reason}")
                return

            # Compute Dynamic Setup Metrics
            setup = self.feature_pipeline.compute_setup_for_new_candle(open_price)
            if not setup or not setup.is_tradable:
                logger.info("No trade: Market in High-Volatility Danger Zone or insufficient data.")
                return

            # ML Probability Check
            p_win = self.ml_model.predict_reversion_probability({
                "atr_pct": setup.atr_pct,
                "rvol": setup.rvol,
                "upper_wick_ratio": setup.upper_wick_ratio,
                "lower_wick_ratio": setup.lower_wick_ratio,
                "hour": now_dt.hour,
                "day_of_week": now_dt.weekday(),
            })

            logger.info(
                f"Setup Identified: Tier {setup.tier} | ATR: {setup.atr_pct}% | RVOL: {setup.rvol} | "
                f"ML Confidence P(Win): {p_win*100:.1f}%"
            )

            # Deploy Dual Limit Bracket if confidence >= 65%
            if p_win >= 0.65:
                balances = await self.broker.get_wallet_balances()
                capital_inr = balances.get("balance_inr", self.config.INITIAL_CAPITAL_INR)
                margin_to_deploy = capital_inr * setup.margin_weight

                await self.order_manager.place_dual_bracket(
                    upper_limit=setup.upper_limit,
                    lower_limit=setup.lower_limit,
                    leverage=setup.leverage,
                    margin_inr=margin_to_deploy,
                    tier=setup.tier,
                )

        # If kline just closed, append to feature pipeline history
        if is_closed:
            self.feature_pipeline.add_completed_kline(kline)

    async def handle_ticker_event(self, ticker: dict):
        """Processes real-time ticks to monitor order fills and position exits."""
        price = ticker["price"]
        self.current_price = price

        # 1. Paper trading fill simulation
        if isinstance(self.broker, MockBroker) and self.order_manager.state == OrderState.BRACKET_ACTIVE:
            fill_events = self.broker.update_price_and_check_fills(price)
            for ev in fill_events:
                await self.order_manager.handle_fill_event(
                    fill_order=ev["order"],
                    target_roi_pct=self.config.TARGET_ROI_PCT,
                    sl_roi_pct=self.config.SL_ROI_PCT,
                )
                if self.order_manager.active_position:
                    await self.notifier.alert_trade_entry({
                        "symbol": self.config.BINANCE_SYMBOL,
                        "side": self.order_manager.active_position.side,
                        "entry_price": self.order_manager.active_position.entry_price,
                        "leverage": self.order_manager.active_position.leverage,
                        "margin_inr": self.order_manager.active_position.margin_inr,
                        "tp_price": self.order_manager.active_position.tp_price,
                        "sl_price": self.order_manager.active_position.sl_price,
                    }, p_win=0.75)

        # 2. Monitor Active Position for TP or SL
        if self.order_manager.state == OrderState.IN_POSITION:
            exit_result = await self.order_manager.check_position_exit(price)
            if exit_result:
                is_win = (exit_result["exit_reason"] == "TP")
                self.risk_manager.record_trade_completion(is_win=is_win)

                # Persist to SQLite
                balances = await self.broker.get_wallet_balances()
                new_bal = balances.get("balance_inr", self.config.INITIAL_CAPITAL_INR)
                self.feature_store.log_trade({
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "candle_num": 0,
                    "session_name": "Active",
                    "tier": "Dynamic",
                    "side": exit_result["side"],
                    "leverage": self.config.BASE_LEVERAGE,
                    "margin_inr": 1000.0,
                    "entry_price": exit_result["entry_price"],
                    "exit_price": exit_result["exit_price"],
                    "exit_reason": exit_result["exit_reason"],
                    "pnl_pct": exit_result["net_roi_pct"],
                    "pnl_inr": exit_result["pnl_inr"],
                    "is_win": 1 if is_win else 0,
                    "atr_pct": 2.0,
                    "rvol": 1.0,
                })

                # Send Telegram alert
                await self.notifier.alert_trade_exit(exit_result, new_balance=new_bal)

    async def handle_liquidation_event(self, liq: dict):
        """Processes live Binance liquidation cascade ticks."""
        self.feature_pipeline.add_liquidation_event(liq)

    async def _heartbeat_loop(self):
        """Sends hourly heartbeat ping to Telegram."""
        while self.is_running:
            await asyncio.sleep(3600)
            balances = await self.broker.get_wallet_balances()
            bal = balances.get("balance_inr", self.config.INITIAL_CAPITAL_INR)
            await self.notifier.alert_heartbeat({
                "state": self.order_manager.state.value,
                "current_price": self.current_price,
                "balance": bal,
                "trades_today": self.risk_manager.daily_trade_count,
                "mode": self.config.EXECUTION_MODE,
            })


def main():
    daemon = TradingDaemon()

    def handle_sigterm(sig, frame):
        logger.info("Signal received. Terminating bot...")
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        asyncio.run(daemon.start())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Trading bot terminated cleanly.")


if __name__ == "__main__":
    main()
