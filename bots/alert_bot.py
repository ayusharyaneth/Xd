from telegram import Bot
from config.settings import settings
from utils.logger import logger

class AlertBot:
    def __init__(self):
        self.bot = Bot(token=settings.ALERT_BOT_TOKEN)
        self.chat_id = settings.ALERT_CHAT_ID

    async def send_alert(self, message: str):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=f"🚨 **SYSTEM ALERT** 🚨\n\n{message}", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send alert telegram: {e}")

alert_bot = AlertBot()
