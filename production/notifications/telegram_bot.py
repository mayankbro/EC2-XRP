"""
production/notifications/telegram_bot.py
Asynchronous Telegram alert and telemetry notifier.
Sends instantaneous push alerts for trade entries, exits, risk events,
and supports remote commands like /status and /kill.
"""

import asyncio
import logging
from typing import Optional
import aiohttp

logger = logging.getLogger("TelegramNotifier")


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self.is_enabled = bool(
            self.bot_token and 
            self.chat_id and 
            "your_telegram" not in self.bot_token
        )
        if not self.is_enabled:
            logger.info("Telegram notification disabled (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing/placeholder).")

    async def send_message(self, text: str):
        """Sends an async formatted Markdown message to Telegram."""
        if not self.is_enabled:
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=8) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        logger.error(f"Telegram API error: {err}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def alert_trade_entry(self, pos_data: dict, p_win: float):
        """Alerts when a limit order fills and position becomes active."""
        side_emoji = "🟢 LONG" if pos_data["side"] == "long" else "🔴 SHORT"
        msg = (
            f"⚡ *NEW POSITION OPENED*\n\n"
            f"*Asset*: `{pos_data['symbol']}`\n"
            f"*Direction*: {side_emoji}\n"
            f"*Entry Price*: `${pos_data['entry_price']:.4f}`\n"
            f"*Leverage*: `{pos_data['leverage']:.0f}x`\n"
            f"*Margin Allocated*: `₹{pos_data['margin_inr']:,.0f}`\n"
            f"*Take Profit (+25%)*: `${pos_data['tp_price']:.4f}`\n"
            f"*Stop Loss (-25%)*: `${pos_data['sl_price']:.4f}`\n"
            f"*ML Confidence P(Win)*: `{p_win*100:.1f}%`\n"
            f"*Execution Venue*: CoinDCX Futures"
        )
        await self.send_message(msg)

    async def alert_trade_exit(self, outcome: dict, new_balance: float):
        """Alerts when an active position is closed."""
        is_tp = outcome["exit_reason"] == "TP"
        res_emoji = "🎉 TARGET HIT (TP)" if is_tp else "⚠️ STOP LOSS TRIGGERED (SL)"
        pnl_sign = "+" if outcome["pnl_inr"] >= 0 else ""

        msg = (
            f"{res_emoji}\n\n"
            f"*Side*: `{outcome['side'].upper()}`\n"
            f"*Exit Price*: `${outcome['exit_price']:.4f}`\n"
            f"*Net ROI*: `{outcome['net_roi_pct']:+.2f}%`\n"
            f"*Realized PnL*: `{pnl_sign}₹{outcome['pnl_inr']:,.2f}`\n"
            f"*New Balance*: `₹{new_balance:,.2f}`\n"
        )
        await self.send_message(msg)

    async def alert_heartbeat(self, status: dict):
        """Sends hourly system heartbeat."""
        msg = (
            f"💓 *BOT HEARTBEAT*\n"
            f"• State: `{status['state']}`\n"
            f"• XRP/USDT: `${status['current_price']:.4f}`\n"
            f"• Balance: `₹{status['balance']:,.2f}`\n"
            f"• Daily Trades: `{status['trades_today']}/1`\n"
            f"• Mode: `{status['mode']}`"
        )
        await self.send_message(msg)
