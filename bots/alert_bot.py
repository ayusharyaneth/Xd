from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from config.settings import settings
from utils.logger import logger

class AlertBot:
    def __init__(self):
        self.app = Application.builder().token(settings.ALERT_BOT_TOKEN).build()
        self.chat_id = settings.ALERT_CHAT_ID
        self.app.add_handler(CommandHandler("start", self.start_cmd))
        # For alert bot we also add /ping for sysadmins convenience
        self.app.add_handler(CommandHandler("ping", self.ping))

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome = (
            "🚨 *Alert Bot* 🚨\n\n"
            "This bot sends system and escalation alerts.\n"
            "Use /ping to check current system health from alert bot."
        )
        keyboard = [
            [
                InlineKeyboardButton("🏓 Ping", callback_data="alert_ping"),
            ]
        ]
        await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # For simplicity we reply with a minimal message. The main /ping is in signal bot.
        await update.message.reply_text("🏓 Alert Bot is running.", parse_mode="Markdown")

    async def send_alert(self, message: str):
        try:
            await self.app.bot.send_message(chat_id=self.chat_id, text=f"🚨 **SYSTEM ALERT** 🚨\n\n{message}", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send alert telegram: {e}")

    async def start(self):
        await self.app.initialize()
        await self.app.start()

    async def stop(self):
        await self.app.stop()
        await self.app.shutdown()

alert_bot = AlertBot()
