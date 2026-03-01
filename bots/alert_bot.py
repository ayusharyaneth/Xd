from telegram.ext import Application
from config.settings import settings
from loguru import logger

class AlertBot:
    def __init__(self):
        self.app = Application.builder().token(settings.env.ALERT_BOT_TOKEN).build()

    async def initialize(self):
        await self.app.initialize()
        await self.app.start()

    async def send_alert(self, message):
        try:
            await self.app.bot.send_message(chat_id=settings.env.ADMIN_CHAT_ID, text=f"⚠️ SYSTEM ALERT:\n{message}")
        except Exception as e:
            logger.error(f"Failed to send system alert: {e}")

    async def shutdown(self):
        await self.app.stop()
        await self.app.shutdown()
