"""
production/risk/circuit_breakers.py
Institutional risk management and circuit breakers:
1. Daily trade quota limiter (strictly 1 trade / day).
2. Weekend trading blocker (Mon-Fri only).
3. 3-strike daily loss kill-switch (locks bot if 2 losses occur).
4. Maximum portfolio drawdown lock (locks bot if drawdown > 15%).
"""

import datetime
import logging
from typing import Optional

logger = logging.getLogger("CircuitBreaker")


class RiskCircuitBreaker:
    def __init__(
        self,
        max_trades_per_day: int = 1,
        max_daily_losses: int = 2,
        max_portfolio_drawdown_pct: float = 15.0,
        no_weekends: bool = True,
    ):
        self.max_trades_per_day = max_trades_per_day
        self.max_daily_losses = max_daily_losses
        self.max_portfolio_drawdown_pct = max_portfolio_drawdown_pct
        self.no_weekends = no_weekends

        # Daily state tracking
        self.current_trade_date: Optional[datetime.date] = None
        self.daily_trade_count: int = 0
        self.daily_loss_count: int = 0
        self.is_emergency_locked: bool = False
        self.lock_reason: str = ""

    def _reset_day_if_needed(self, current_date: datetime.date):
        if self.current_trade_date != current_date:
            self.current_trade_date = current_date
            self.daily_trade_count = 0
            self.daily_loss_count = 0
            logger.info(f"Risk Manager: Reset daily counters for {current_date}")

    def can_open_new_trade(self, current_dt: datetime.datetime, current_drawdown_pct: float = 0.0) -> tuple[bool, str]:
        """
        Evaluates whether a new trade is permitted under current risk parameters.
        Returns (is_allowed, reason).
        """
        current_date = current_dt.date()
        self._reset_day_if_needed(current_date)

        # 1. Manual Emergency Lock
        if self.is_emergency_locked:
            return False, f"Bot is EMERGENCY LOCKED: {self.lock_reason}"

        # 2. Weekend Check (0=Mon, 6=Sun)
        if self.no_weekends and current_dt.weekday() in [5, 6]:
            return False, f"Weekend trading blocked (Day {current_dt.strftime('%A')})"

        # 3. Maximum Drawdown Check
        if current_drawdown_pct >= self.max_portfolio_drawdown_pct:
            self.is_emergency_locked = True
            self.lock_reason = f"Max Drawdown Exceeded: {current_drawdown_pct:.1f}% >= {self.max_portfolio_drawdown_pct}%"
            logger.critical(self.lock_reason)
            return False, self.lock_reason

        # 4. Daily Loss Limit Check
        if self.daily_loss_count >= self.max_daily_losses:
            return False, f"Daily loss limit reached ({self.daily_loss_count} losses today)"

        # 5. Max Trades Per Day Check
        if self.daily_trade_count >= self.max_trades_per_day:
            return False, f"Daily trade quota reached ({self.daily_trade_count}/{self.max_trades_per_day} trades today)"

        return True, "Trade permitted"

    def record_trade_completion(self, is_win: bool):
        """Updates internal risk counters after a trade closes."""
        self.daily_trade_count += 1
        if not is_win:
            self.daily_loss_count += 1

        logger.info(
            f"Risk state updated: Trades today: {self.daily_trade_count}/{self.max_trades_per_day} | "
            f"Losses today: {self.daily_loss_count}/{self.max_daily_losses}"
        )

    def trigger_emergency_kill(self, reason: str = "Manual User Kill Switch"):
        """Instantly disables trading."""
        self.is_emergency_locked = True
        self.lock_reason = reason
        logger.warning(f"EMERGENCY KILL SWITCH TRIGGERED: {reason}")
