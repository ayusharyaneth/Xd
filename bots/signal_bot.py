import asyncio
import time
from typing import Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from config.settings import settings
from system.health import health_monitor
from system.self_defense import self_defense
from engines.regime import regime_analyzer
from watch.watch_manager import watch_manager
from utils.logger import logger

class SignalBot:
    def __init__(self):
        self.app = Application.builder().token(settings.SIGNAL_BOT_TOKEN).build()
        self.chat_id = settings.SIGNAL_CHAT_ID
        # register handlers
        self.app.add_handler(CommandHandler("ping", self.ping))
        self.app.add_handler(CommandHandler("watch", self.cmd_watch))
        self.app.add_handler(CommandHandler("start", self.start_cmd))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        # a lock to guard send_signal concurrency to avoid hitting duplicate race conditions
        self._send_lock = asyncio.Lock()

    # /start handler
    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome = (
            "👋 *Welcome to DexScreener Intelligence Signal Bot*\n\n"
            "Use the buttons below for quick actions:\n"
            "• /ping — Health & status\n"
            "• /watch — List active watches\n\n"
            "Inline buttons provide quick single-click actions when you receive signals."
        )
        keyboard = [
            [
                InlineKeyboardButton("🏓 Ping", callback_data="ping"),
                InlineKeyboardButton("👀 Watchlist", callback_data="list_watch")
            ],
            [
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=reply_markup)

    # /ping handler
    async def ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        health = health_monitor.get_system_health()
        regime = regime_analyzer.current_regime
        sm_state = "🟢 INACTIVE" if not self_defense.is_safe_mode() else "🔴 ACTIVE"
        watch_count = await watch_manager.count()

        msg = (
            f"🏓 **System Status**\n"
            f"Status: {'🟢 Healthy' if health['healthy'] else '🔴 Degraded'}\n"
            f"Latency: {health['avg_latency_ms']:.2f}ms\n"
            f"CPU: {health['cpu_percent']}%\n"
            f"Memory: {health['memory_percent']}%\n"
            f"Market Regime: {regime}\n"
            f"Safe Mode: {sm_state}\n"
            f"Active Watches: {watch_count}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    # /watch command to list watches
    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        watches = await watch_manager.list_watches()
        if not watches:
            await update.message.reply_text("No active watches at the moment.")
            return
        messages = []
        for w in watches:
            addr = w["address"]
            expires_in = w["expires_in"]
            esc = " (Escalated)" if w.get("escalated") else ""
            messages.append(f"`{addr}` — expires in {expires_in}s{esc}")
        text = "*Active Watches:*\n" + "\n".join(messages)
        # include buttons to remove all watches or refresh
        keyboard = [
            [InlineKeyboardButton("🗑 Remove All Watches", callback_data="remove_all_watches")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="list_watch")]
        ]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    # Single method to send a signal with buttons
    async def send_signal(self, text: str, token_address: str):
        """
        Sends a Telegram message to the configured chat_id with inline actions.
        This method is protected by _send_lock to avoid overlapping sends that may cause duplicate alerts.
        """
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh|{token_address}"),
                InlineKeyboardButton("👁 Watch", callback_data=f"watch|{token_address}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        async with self._send_lock:
            try:
                await self.app.bot.send_message(chat_id=self.chat_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send signal: {e}")

    async def send_watch_alert(self, token_address: str, reason: str):
        msg = f"⚠️ **WATCH ESCALATION** ⚠️\nToken: `{token_address}`\nReason: {reason}\nAction: Consider Exit."
        try:
            await self.app.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send watch alert: {e}")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data or ""
        # direct ping/list_watch/help actions from /start buttons
        if data == "ping":
            # emulate /ping behavior
            health = health_monitor.get_system_health()
            regime = regime_analyzer.current_regime
            sm_state = "🟢 INACTIVE" if not self_defense.is_safe_mode() else "🔴 ACTIVE"
            watch_count = await watch_manager.count()
            msg = (
                f"🏓 **System Status**\n"
                f"Status: {'🟢 Healthy' if health['healthy'] else '🔴 Degraded'}\n"
                f"Latency: {health['avg_latency_ms']:.2f}ms\n"
                f"CPU: {health['cpu_percent']}%\n"
                f"Memory: {health['memory_percent']}%\n"
                f"Market Regime: {regime}\n"
                f"Safe Mode: {sm_state}\n"
                f"Active Watches: {watch_count}"
            )
            await query.edit_message_text(msg, parse_mode="Markdown")
            return
        if data == "help":
            help_text = (
                "Help & Commands:\n"
                "/ping - Get system health\n"
                "/watch - List watches\n\n"
                "When signals arrive you can click *Watch* to add token to watchlist or *Refresh* to refresh details."
            )
            await query.edit_message_text(help_text, parse_mode="Markdown")
            return
        if data == "list_watch":
            watches = await watch_manager.list_watches()
            if not watches:
                await query.edit_message_text("No active watches at the moment.")
                return
            messages = []
            for w in watches:
                addr = w["address"]
                expires_in = w["expires_in"]
                esc = " (Escalated)" if w.get("escalated") else ""
                messages.append(f"`{addr}` — expires in {expires_in}s{esc}")
            text = "*Active Watches:*\n" + "\n".join(messages)
            keyboard = [
                [InlineKeyboardButton("🗑 Remove All Watches", callback_data="remove_all_watches")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="list_watch")]
            ]
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        if data == "remove_all_watches":
            # remove all watches
            watches = await watch_manager.list_watches()
            for w in watches:
                await watch_manager.remove_watch(w["address"])
            await query.edit_message_text("All watches removed.")
            return

        # parse token-specific callback_data like "watch|address" or "refresh|address"
        if "|" in data:
            action, address = data.split("|", 1)
            if action == "watch":
                # Add to watchlist
                # For safety, attempt to fetch any pair data stored in message (if present)
                # As fallback, store minimal data with address
                pair_data = {"address": address, "added_via": "signal_button", "timestamp": time.time()}
                await watch_manager.add_watch(address, pair_data)
                # update message to reflect success
                try:
                    await query.edit_message_text(text=f"{query.message.text}\n\n*👀 Token added to Watchlist!*", parse_mode="Markdown")
                except Exception:
                    # fallback reply
                    await query.message.reply_text("👀 Token added to Watchlist!")
            elif action == "refresh":
                # For demo: just edit message with a "refreshed" note
                try:
                    await query.edit_message_text(text=f"{query.message.text}\n\n*🔄 Data Refreshed!*", parse_mode="Markdown")
                except Exception:
                    await query.message.reply_text("🔄 Data Refreshed!")
            return

    async def start(self):
        # Initialize the application and start the background polling handled in main.py
        await self.app.initialize()
        await self.app.start()
        # we won't call run_polling here since main.py manages event loop and lifecycle

    async def stop(self):
        await self.app.stop()
        await self.app.shutdown()

signal_bot = SignalBot()
