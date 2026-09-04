"""
production/execution/order_manager.py
Manages the live order lifecycle:
1. Places Dual-Limit OCO Bracket at 4H candle open.
2. Cancels opposite order immediately when one is filled (OCO).
3. Manages TP (+25%) and SL (-25%) exits and time-based closures.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("OrderManager")


class OrderState(Enum):
    IDLE = "IDLE"
    BRACKET_ACTIVE = "BRACKET_ACTIVE"
    IN_POSITION = "IN_POSITION"
    TRADE_COMPLETED = "TRADE_COMPLETED"


@dataclass
class ActivePosition:
    side: str               # "long" or "short"
    entry_price: float
    quantity: float
    leverage: float
    margin_inr: float
    tp_price: float
    sl_price: float
    entry_time: str
    tier: str


class OrderManager:
    def __init__(self, broker_client, pair: str = "B-XRP_USDT", inr_usd_rate: float = 87.0):
        self.broker = broker_client
        self.pair = pair
        self.inr_usd_rate = inr_usd_rate  # Conversion for INR margin sizing
        self.state = OrderState.IDLE

        # Tracking orders
        self.upper_order_id: Optional[str] = None
        self.lower_order_id: Optional[str] = None
        self.active_position: Optional[ActivePosition] = None

    async def place_dual_bracket(
        self,
        upper_limit: float,
        lower_limit: float,
        leverage: float,
        margin_inr: float,
        tier: str,
    ):
        """Places Limit Sell at upper sweep band & Limit Buy at lower sweep band."""
        # Convert INR margin to position quantity (USDT notional)
        margin_usd = margin_inr / self.inr_usd_rate
        notional_usd = margin_usd * leverage

        # XRP Quantity = Notional USD / Price
        qty_upper = round(notional_usd / upper_limit, 1)
        qty_lower = round(notional_usd / lower_limit, 1)

        logger.info(
            f"Deploying OCO Bracket: Margin ₹{margin_inr:,.0f} | Lev: {leverage}x | "
            f"Upper Short: ${upper_limit:.4f} ({qty_upper} XRP) | Lower Long: ${lower_limit:.4f} ({qty_lower} XRP)"
        )

        # 1. Place Upper Short Limit
        res_u = await self.broker.create_futures_order(
            pair=self.pair,
            side="sell",
            order_type="limit_order",
            price=upper_limit,
            quantity=qty_upper,
            leverage=leverage,
            client_order_id="bracket_upper_short",
        )
        self.upper_order_id = res_u.get("order_id", "bracket_upper_short")

        # 2. Place Lower Long Limit
        res_l = await self.broker.create_futures_order(
            pair=self.pair,
            side="buy",
            order_type="limit_order",
            price=lower_limit,
            quantity=qty_lower,
            leverage=leverage,
            client_order_id="bracket_lower_long",
        )
        self.lower_order_id = res_l.get("order_id", "bracket_lower_long")

        self.state = OrderState.BRACKET_ACTIVE

    async def handle_fill_event(self, fill_order: dict, target_roi_pct: float = 25.0, sl_roi_pct: float = 25.0):
        """Called when one of the dual limit orders fills."""
        side = fill_order["side"].lower()
        fill_price = fill_order.get("fill_price", fill_order["price"])
        qty = fill_order["quantity"]
        lev = fill_order["leverage"]

        target_delta = (target_roi_pct / lev) / 100.0
        sl_delta = (sl_roi_pct / lev) / 100.0

        if side == "sell":  # Short entered
            # Cancel opposite Long order immediately (OCO)
            if self.lower_order_id:
                await self.broker.cancel_order(self.lower_order_id)
                self.lower_order_id = None

            tp_price = fill_price * (1.0 - target_delta)
            sl_price = fill_price * (1.0 + sl_delta)
            pos_side = "short"

        else:  # Long entered
            # Cancel opposite Short order immediately (OCO)
            if self.upper_order_id:
                await self.broker.cancel_order(self.upper_order_id)
                self.upper_order_id = None

            tp_price = fill_price * (1.0 + target_delta)
            sl_price = fill_price * (1.0 - sl_delta)
            pos_side = "long"

        self.active_position = ActivePosition(
            side=pos_side,
            entry_price=fill_price,
            quantity=qty,
            leverage=lev,
            margin_inr=(qty * fill_price / lev) * self.inr_usd_rate,
            tp_price=round(tp_price, 5),
            sl_price=round(sl_price, 5),
            entry_time="now",
            tier="Active",
        )
        self.state = OrderState.IN_POSITION
        logger.info(f"Position ACTIVE: {pos_side.upper()} @ ${fill_price:.4f} | TP: ${tp_price:.4f} | SL: ${sl_price:.4f}")

    async def check_position_exit(self, current_price: float) -> Optional[dict]:
        """Monitors active position against TP and SL trigger levels."""
        if self.state != OrderState.IN_POSITION or not self.active_position:
            return None

        pos = self.active_position
        is_tp = False
        is_sl = False

        if pos.side == "long":
            if current_price >= pos.tp_price:
                is_tp = True
            elif current_price <= pos.sl_price:
                is_sl = True
        else:  # short
            if current_price <= pos.tp_price:
                is_tp = True
            elif current_price >= pos.sl_price:
                is_sl = True

        if is_tp or is_sl:
            exit_reason = "TP" if is_tp else "SL"
            exit_price = pos.tp_price if is_tp else pos.sl_price

            # Calculate realized PnL in INR
            if pos.side == "long":
                price_ret = (exit_price - pos.entry_price) / pos.entry_price
            else:
                price_ret = (pos.entry_price - exit_price) / pos.entry_price

            roi_pct = price_ret * pos.leverage * 100.0
            fee_on_margin = (0.0002 + (0.0002 if is_tp else 0.0005)) * pos.leverage * 100.0
            net_roi_pct = roi_pct - fee_on_margin
            pnl_inr = pos.margin_inr * (net_roi_pct / 100.0)

            # Update broker
            if hasattr(self.broker, "register_trade_outcome"):
                self.broker.register_trade_outcome(pnl_inr)

            result = {
                "side": pos.side,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "net_roi_pct": round(net_roi_pct, 2),
                "pnl_inr": round(pnl_inr, 2),
            }

            self.state = OrderState.TRADE_COMPLETED
            self.active_position = None
            logger.info(f"Trade Closed: {exit_reason} | Net ROI: {net_roi_pct:+.2f}% | PnL: ₹{pnl_inr:+,.2f}")
            return result

        return None

    async def cancel_active_brackets(self):
        """Cancels unfilled bracket orders when 4H window ends."""
        if self.upper_order_id:
            await self.broker.cancel_order(self.upper_order_id)
            self.upper_order_id = None
        if self.lower_order_id:
            await self.broker.cancel_order(self.lower_order_id)
            self.lower_order_id = None
        self.state = OrderState.IDLE
