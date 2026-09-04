"""
production/execution/coindcx_client.py
Production REST client for CoinDCX Futures API.
Implements secure HMAC SHA-256 request signing, nonce synchronization,
order execution, position tracking, and wallet balance querying.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional
import aiohttp

logger = logging.getLogger("CoinDCXClient")


class CoinDCXClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.coindcx.com",
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _sign_payload(self, body: dict) -> Dict[str, str]:
        """Generates HMAC-SHA256 signature for CoinDCX authenticated requests."""
        body_json = json.dumps(body, separators=(",", ":"))
        secret_bytes = bytes(self.api_secret, encoding="utf-8")
        signature = hmac.new(secret_bytes, body_json.encode(), hashlib.sha256).hexdigest()

        return {
            "Content-Type": "application/json",
            "X-AUTH-APIKEY": self.api_key,
            "X-AUTH-SIGNATURE": signature,
        }

    async def get_wallet_balances(self) -> Dict[str, Any]:
        """Queries account balance and margin availability."""
        url = f"{self.base_url}/exchange/v1/users/balances"
        timestamp = int(time.time() * 1000)
        body = {"timestamp": timestamp}
        headers = self._sign_payload(body)

        session = await self._get_session()
        try:
            async with session.post(url, json=body, headers=headers, timeout=10) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"Failed to fetch balances: {e}")
            return {"error": str(e)}

    async def create_futures_order(
        self,
        pair: str,
        side: str,  # "buy" or "sell"
        order_type: str,  # "limit_order" or "market_order"
        price: float,
        quantity: float,
        leverage: float = 15.0,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submits an order to the CoinDCX Derivatives/Futures engine.
        """
        url = f"{self.base_url}/exchange/v1/derivatives/futures/orders/create"
        timestamp = int(time.time() * 1000)
        body = {
            "timestamp": timestamp,
            "order": {
                "pair": pair,
                "side": side.lower(),
                "order_type": order_type.lower(),
                "price": price,
                "total_quantity": quantity,
                "leverage": leverage,
                "notification": "no_notification",
                "time_in_force": "good_till_cancel",
            }
        }
        if client_order_id:
            body["order"]["client_order_id"] = client_order_id

        headers = self._sign_payload(body)
        session = await self._get_session()
        try:
            async with session.post(url, json=body, headers=headers, timeout=10) as resp:
                data = await resp.json()
                logger.info(f"CoinDCX Order submitted: {side} {quantity} @ {price} | Response: {data}")
                return data
        except Exception as e:
            logger.error(f"Order submission error: {e}")
            return {"error": str(e)}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancels an active order by CoinDCX order ID."""
        url = f"{self.base_url}/exchange/v1/derivatives/futures/orders/cancel"
        timestamp = int(time.time() * 1000)
        body = {
            "timestamp": timestamp,
            "id": order_id,
        }
        headers = self._sign_payload(body)
        session = await self._get_session()
        try:
            async with session.post(url, json=body, headers=headers, timeout=10) as resp:
                data = await resp.json()
                logger.info(f"Canceled order {order_id}: {data}")
                return data
        except Exception as e:
            logger.error(f"Cancel order error: {e}")
            return {"error": str(e)}

    async def get_active_positions(self) -> List[Dict[str, Any]]:
        """Queries currently open futures positions."""
        url = f"{self.base_url}/exchange/v1/derivatives/futures/positions"
        timestamp = int(time.time() * 1000)
        body = {"timestamp": timestamp}
        headers = self._sign_payload(body)
        session = await self._get_session()
        try:
            async with session.post(url, json=body, headers=headers, timeout=10) as resp:
                data = await resp.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []
