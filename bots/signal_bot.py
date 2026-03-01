from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
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
        
        self.app.add_handler(CommandHandler("ping", self.ping))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))

    async def ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        health = health_monitor.get_system_health()
        regime = regime_analyzer.current_regime
        sm_state = "🟢 INACTIVE" if not self_defense.is_safe_mode() else "🔴 ACTIVE"
        watch_count = watch_manager.get_count()

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

    async def send_signal(self, text: str, token_address: str):
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh|{token_address}"),
                InlineKeyboardButton("👁 Watch", callback_data=f"watch|{token_address}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
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
        
        action, address = query.data.split("|")
        if action == "watch":
            watch_manager.add_watch(address, {"address": address}) # mock data injection
            await query.edit_message_text(text=f"{query.message.text}\n\n*👀 Token added to Watchlist!*", parse_mode="Markdown")
        elif action == "refresh":
            await query.edit_message_text(text=f"{query.message.text}\n\n*🔄 Data Refreshed!*", parse_mode="Markdown")

    async def start(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

    async def stop(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

signal_bot = SignalBot()
