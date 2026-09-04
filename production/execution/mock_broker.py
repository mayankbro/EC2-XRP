"""
production/execution/mock_broker.py
In-memory paper trading simulation broker.
Mirrors the exact CoinDCX API interface to enable zero-risk dry runs,
testing bracket logic, fills, and balance tracking in real market time.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MockBroker")


class MockBroker:
    def __init__(self, initial_capital_inr: float = 10000.0):
        self.capital_inr = initial_capital_inr
        self.orders: Dict[str, dict] = {}
        self.positions: List[dict] = []
        self.trade_history: List[dict] = []
        logger.info(f"MockBroker initialized with virtual capital: ₹{self.capital_inr:,.2f}")

    async def get_wallet_balances(self) -> Dict[str, Any]:
        return {
            "balance_inr": round(self.capital_inr, 2),
            "free_margin": round(self.capital_inr, 2),
            "open_positions": len(self.positions),
        }

    async def create_futures_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        price: float,
        quantity: float,
        leverage: float = 15.0,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        order_id = client_order_id or f"mock_{uuid.uuid4().hex[:8]}"
        order = {
            "id": order_id,
            "pair": pair,
            "side": side.lower(),
            "order_type": order_type.lower(),
            "price": price,
            "quantity": quantity,
            "leverage": leverage,
            "status": "open",
        }
        self.orders[order_id] = order
        logger.info(f"[PAPER TRADING] Order placed: {order_id} | {side.upper()} {quantity:.1f} {pair} @ ${price:.4f} (Lev: {leverage}x)")
        return {"status": "success", "order_id": order_id, "data": order}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            self.orders[order_id]["status"] = "canceled"
            logger.info(f"[PAPER TRADING] Order canceled: {order_id}")
            return {"status": "success", "id": order_id}
        return {"status": "error", "message": "Order not found"}

    async def get_active_positions(self) -> List[Dict[str, Any]]:
        return [p for p in self.positions if p.get("status") == "open"]

    def update_price_and_check_fills(self, current_price: float) -> List[dict]:
        """
        Called on every live ticker/kline tick.
        Checks if limit orders fill, triggers bracket state changes.
        """
        events = []
        for o_id, o in list(self.orders.items()):
            if o["status"] != "open":
                continue

            side = o["side"]
            limit_price = o["price"]

            # Long Limit fills when price drops to or below limit
            # Short Limit fills when price rises to or above limit
            filled = (side == "buy" and current_price <= limit_price) or \
                     (side == "sell" and current_price >= limit_price)

            if filled:
                o["status"] = "filled"
                o["fill_price"] = current_price
                events.append({"type": "FILL", "order": o})
                logger.info(f"[PAPER TRADING] ⚡ Order FILLED: {o['side'].upper()} @ ${current_price:.4f}")

        return events

    def register_trade_outcome(self, pnl_inr: float):
        """Updates virtual portfolio balance upon trade exit."""
        self.capital_inr += pnl_inr
        logger.info(f"[PAPER TRADING] Balance updated: PnL: ₹{pnl_inr:,.2f} | New Capital: ₹{self.capital_inr:,.2f}")
