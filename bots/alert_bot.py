from telegram.ext import Application
from config.settings import settings
from utils.logger import log

class AlertBot:
    """
    Bot dedicated to system health and critical errors.
    """
    def __init__(self):
        self.app = Application.builder().token(settings.ALERT_BOT_TOKEN).build()

    async def initialize(self):
        await self.app.initialize()
        await self.app.start()

    async def send_system_alert(self, message: str):
        for admin_id in settings.get_admins():
            try:
                await self.app.bot.send_message(
                    chat_id=admin_id,
                    text=f"🚨 **SYSTEM ALERT** 🚨\n\n{message}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                log.error(f"Failed to send alert to {admin_id}: {e}")

    async def shutdown(self):
        await self.app.stop()
        await self.app.shutdown()
