"""
production/data_feed/binance_ws.py
Asynchronous real-time WebSocket client for Binance Futures.
Streams 4H klines, live liquidation cascades (@forceOrder), and real-time prices.
"""

import asyncio
import json
import logging
from typing import Callable, Optional
import websockets

logger = logging.getLogger("BinanceWS")


class BinanceFuturesStream:
    def __init__(
        self,
        symbol: str = "XRPUSDT",
        on_kline: Optional[Callable] = None,
        on_liquidation: Optional[Callable] = None,
        on_ticker: Optional[Callable] = None,
    ):
        self.symbol = symbol.lower()
        self.on_kline = on_kline
        self.on_liquidation = on_liquidation
        self.on_ticker = on_ticker
        self.is_running = False
        self._ws = None

    async def start(self):
        """Starts the multi-stream WebSocket connection with auto-reconnect."""
        self.is_running = True
        streams = [
            f"{self.symbol}@kline_4h",
            f"{self.symbol}@forceOrder",
            f"{self.symbol}@ticker",
        ]
        stream_path = "/".join(streams)
        url = f"wss://fstream.binance.com/stream?streams={stream_path}"

        logger.info(f"Connecting to Binance Futures WebSocket: {url}")

        while self.is_running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    self._ws = ws
                    logger.info("Binance Futures WebSocket connected successfully.")
                    while self.is_running:
                        message = await ws.recv()
                        data = json.loads(message)
                        await self._route_message(data)
            except (websockets.ConnectionClosed, websockets.WebSocketException) as e:
                logger.warning(f"WebSocket disconnected: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected WebSocket error: {e}. Retrying in 10s...")
                await asyncio.sleep(10)

    async def stop(self):
        """Gracefully shuts down the stream."""
        self.is_running = False
        if self._ws:
            await self._ws.close()
            logger.info("Binance Futures WebSocket stopped.")

    async def _route_message(self, msg: dict):
        """Dispatches incoming stream events to appropriate handlers."""
        stream = msg.get("stream", "")
        data = msg.get("data", {})

        if "@kline" in stream:
            k = data.get("k", {})
            kline_payload = {
                "start_time": k.get("t"),
                "close_time": k.get("T"),
                "symbol": k.get("s"),
                "open": float(k.get("o")),
                "high": float(k.get("h")),
                "low": float(k.get("l")),
                "close": float(k.get("c")),
                "volume": float(k.get("v")),
                "is_closed": k.get("x", False),
            }
            if self.on_kline:
                await self.on_kline(kline_payload)

        elif "@forceOrder" in stream:
            o = data.get("o", {})
            liq_payload = {
                "symbol": o.get("s"),
                "side": o.get("S"),  # SELL (Long liquidated) or BUY (Short liquidated)
                "order_type": o.get("o"),
                "original_quantity": float(o.get("q", 0.0)),
                "price": float(o.get("p", 0.0)),
                "average_price": float(o.get("ap", 0.0)),
                "timestamp": o.get("T"),
            }
            if self.on_liquidation:
                await self.on_liquidation(liq_payload)

        elif "@ticker" in stream:
            ticker_payload = {
                "symbol": data.get("s"),
                "price": float(data.get("c", 0.0)),
                "high_24h": float(data.get("h", 0.0)),
                "low_24h": float(data.get("l", 0.0)),
                "volume_24h": float(data.get("v", 0.0)),
            }
            if self.on_ticker:
                await self.on_ticker(ticker_payload)
