"""
production/ml/feature_store.py
SQLite-backed feature store and persistent trade database.
Records live market features, execution outcomes, and provides
training datasets for online continual machine learning.
"""

import sqlite3
import logging
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger("FeatureStore")


class FeatureStore:
    def __init__(self, db_path: str = "data/live_trading.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes database schema if tables do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Trade execution logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    candle_num INTEGER,
                    session_name TEXT,
                    tier TEXT,
                    side TEXT NOT NULL,
                    leverage REAL,
                    margin_inr REAL,
                    entry_price REAL,
                    exit_price REAL,
                    exit_reason TEXT,
                    pnl_pct REAL,
                    pnl_inr REAL,
                    is_win INTEGER,
                    atr_pct REAL,
                    rvol REAL
                )
            """)

            # Model performance tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS model_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trained_at TEXT NOT NULL,
                    sample_count INTEGER,
                    train_accuracy REAL,
                    val_accuracy REAL,
                    auc_score REAL,
                    weights_path TEXT
                )
            """)
            conn.commit()

    def log_trade(self, trade_data: dict):
        """Persists a completed trade record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO live_trades (
                    timestamp, candle_num, session_name, tier, side,
                    leverage, margin_inr, entry_price, exit_price,
                    exit_reason, pnl_pct, pnl_inr, is_win, atr_pct, rvol
                ) VALUES (
                    :timestamp, :candle_num, :session_name, :tier, :side,
                    :leverage, :margin_inr, :entry_price, :exit_price,
                    :exit_reason, :pnl_pct, :pnl_inr, :is_win, :atr_pct, :rvol
                )
            """, trade_data)
            conn.commit()
            logger.info(f"Trade successfully logged to SQLite: ID {cursor.lastrowid}")

    def get_recent_trades(self, limit: int = 50) -> List[dict]:
        """Retrieves recent trades for monitoring and display."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM live_trades ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_training_dataset(self) -> pd.DataFrame:
        """Loads logged trades as training features for model updates."""
        with self._get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM live_trades", conn)
