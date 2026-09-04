"""
production/config.py
Centralized configuration management for the autonomous trading bot.
Loads environment variables, API credentials, and risk parameters.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


@dataclass(frozen=True)
class TradingConfig:
    # Execution Mode: "MOCK" (paper trading simulator) or "LIVE" (real CoinDCX orders)
    EXECUTION_MODE: str = os.getenv("EXECUTION_MODE", "MOCK").upper()

    # Asset & Pair
    BINANCE_SYMBOL: str = os.getenv("BINANCE_SYMBOL", "XRPUSDT")
    COINDCX_SYMBOL: str = os.getenv("COINDCX_SYMBOL", "B-XRP_USDT")  # CoinDCX futures format
    BASE_INTERVAL: str = "4h"

    # Strategy Parameters
    BASE_LEVERAGE: float = float(os.getenv("BASE_LEVERAGE", "15.0"))
    A_PLUS_LEVERAGE: float = float(os.getenv("A_PLUS_LEVERAGE", "20.0"))
    TARGET_ROI_PCT: float = float(os.getenv("TARGET_ROI_PCT", "25.0"))
    SL_ROI_PCT: float = float(os.getenv("SL_ROI_PCT", "25.0"))

    # Sizing
    INITIAL_CAPITAL_INR: float = float(os.getenv("INITIAL_CAPITAL_INR", "10000.0"))
    STANDARD_MARGIN_WEIGHT: float = float(os.getenv("STANDARD_MARGIN_WEIGHT", "0.10"))  # 10%
    A_PLUS_MARGIN_WEIGHT: float = float(os.getenv("A_PLUS_MARGIN_WEIGHT", "0.15"))    # 15%

    # Volatility Regimes (4-candle ATR %)
    A_PLUS_MAX_ATR: float = 1.8
    DANGER_MIN_ATR: float = 3.2

    # Circuit Breakers
    MAX_TRADES_PER_DAY: int = 1
    MAX_CONSECUTIVE_LOSSES: int = 2
    MAX_DAILY_LOSS_PCT: float = 5.0
    MAX_DRAWDOWN_LOCK_PCT: float = 15.0

    # API Endpoints
    BINANCE_REST_BASE: str = "https://fapi.binance.com"
    BINANCE_WS_BASE: str = "wss://fstream.binance.com/ws"
    COINDCX_REST_BASE: str = os.getenv("COINDCX_REST_BASE", "https://api.coindcx.com")

    # API Credentials
    COINDCX_API_KEY: str = os.getenv("COINDCX_API_KEY", "")
    COINDCX_API_SECRET: str = os.getenv("COINDCX_API_SECRET", "")

    # Telemetry & Alerting
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Persistence
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/live_trading.db")
    MODEL_WEIGHTS_PATH: str = os.getenv("MODEL_WEIGHTS_PATH", "production/ml/model_weights.pkl")


CONFIG = TradingConfig()
