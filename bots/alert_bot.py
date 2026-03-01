from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from config.settings import settings
from utils.logger import logger
from datetime import datetime

class AlertBot:
    def __init__(self):
        self.app = Application.builder().token(settings.ALERT_BOT_TOKEN).build()
        self.chat_id = settings.ALERT_CHAT_ID

        # Add command handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("status", self.status))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome message for Alert Bot"""
        welcome_text = (
            "🚨 **System Alert Bot Activated**\n\n"
            "This bot sends critical system notifications:\n"
            "• Safe Mode activations\n"
            "• API failures\n"
            "• System resource alerts\n"
            "• Escalation warnings\n\n"
            "⚠️ *Keep this bot unmuted for critical alerts.*"
        )

        keyboard = [
            [
                InlineKeyboardButton("🔍 Check System Status", callback_data="sys_status"),
                InlineKeyboardButton("📋 View Recent Alerts", callback_data="recent_alerts")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Quick status check for alert bot"""
        await update.message.reply_text(
            "✅ **Alert Bot is operational**\n"
            f"Monitoring chat: {self.chat_id}\n"
            "Ready to send critical alerts.",
            parse_mode="Markdown"
        )

    async def send_alert(self, message: str):
        """Send system alert to admin"""
        try:
            full_message = (
                f"🚨 **SYSTEM ALERT** 🚨\n\n"
                f"{message}\n\n"
                f"_Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
            )
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=full_message,
                parse_mode="Markdown"
            )
            logger.info(f"Alert sent: {message[:50]}...")
        except Exception as e:
            logger.error(f"Failed to send alert telegram: {e}")

    async def start_bot(self):
        """Start the alert bot - using run_polling with drop_pending_updates"""
        # Store the task for later shutdown
        self._polling_task = asyncio.create_task(
            self.app.run_polling(allowed_updates=Update.ALL_TYPES)
        )
        logger.info("Alert Bot started")

    async def stop_bot(self):
        """Stop the alert bot"""
        try:
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Alert Bot stopped")
        except Exception as e:
            logger.error(f"Error stopping alert bot: {e}")

# Import asyncio here to avoid circular import issues
import asyncio
alert_bot = AlertBot()
