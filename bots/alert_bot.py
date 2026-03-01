from telegram.ext import Application
from config.settings import settings
from utils.logger import log
from datetime import datetime
import asyncio

class AlertBot:
    """
    Bot dedicated to system health, critical errors, and lifecycle status updates.
    """
    def __init__(self):
        self.app = Application.builder().token(settings.ALERT_BOT_TOKEN).build()

    async def initialize(self):
        await self.app.initialize()
        await self.app.start()
        # Admin bot polling is minimal, mainly for keeping the session alive for sending
        await self.app.updater.start_polling(drop_pending_updates=True)

    async def send_system_alert(self, message: str):
        """Generic system alert broadcaster."""
        for admin_id in settings.get_admins():
            try:
                await self.app.bot.send_message(
                    chat_id=admin_id,
                    text=f"🚨 **SYSTEM ALERT** 🚨\n\n{message}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                log.error(f"Failed to send alert to {admin_id}: {e}")

    async def send_startup_alert(self):
        """Broadcasts ONLINE status."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = (
            f"🟢 **Bot Status: ONLINE**\n"
            f"📡 Monitoring Started\n"
            f"🕒 `{timestamp}`\n"
            f"🛡 Safe Mode: {'Active' if settings.thresholds.get('safe_mode_cpu') else 'Ready'}"
        )
        await self._broadcast_lifecycle_msg(msg)

    async def send_shutdown_alert(self, reason="Manual Stop/Signal"):
        """Broadcasts OFFLINE status. Critical for knowing if bot died."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = (
            f"🔴 **Bot Status: OFFLINE**\n"
            f"⚠ Disconnected from VPS\n"
            f"📝 Reason: `{reason}`\n"
            f"🕒 `{timestamp}`"
        )
        await self._broadcast_lifecycle_msg(msg)

    async def _broadcast_lifecycle_msg(self, msg: str):
        """Helper to broadcast messages to all admins safely."""
        for admin_id in settings.get_admins():
            try:
                # Set a short timeout to prevent shutdown hanging on network issues
                await asyncio.wait_for(
                    self.app.bot.send_message(chat_id=admin_id, text=msg, parse_mode='Markdown'),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                log.error(f"Timeout sending lifecycle alert to {admin_id}")
            except Exception as e:
                log.error(f"Failed to send lifecycle alert to {admin_id}: {e}")

    async def shutdown(self):
        if self.app.updater.running:
            await self.app.updater.stop()
        if self.app.running:
            await self.app.stop()
        await self.app.shutdown()
