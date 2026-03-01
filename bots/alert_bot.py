# ============================================================
# ALERT BOT - Telegram Bot for System Alerts
# ============================================================

import asyncio
from typing import Optional
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, format_duration


logger = get_logger("alert_bot")


class AlertBot:
    """Telegram bot for system alerts and notifications"""
    
    def __init__(self):
        self.config = get_config()
        self.token = self.config.settings.ALERT_BOT_TOKEN
        self.chat_id = self.config.settings.ALERT_CHAT_ID
        self.admin_chat_id = self.config.settings.ADMIN_CHAT_ID
        self.application: Optional[Application] = None
        self._is_running = False
    
    async def initialize(self):
        """Initialize the bot"""
        if not self.token:
            logger.error("Alert bot token not configured")
            return False
        
        try:
            self.application = Application.builder().token(self.token).build()
            
            # Add handlers
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            
            await self.application.initialize()
            await self.application.start()
            
            self._is_running = True
            logger.info("Alert bot initialized")
            return True
        
        except Exception as e:
            logger.error(f"Failed to initialize alert bot: {e}")
            return False
    
    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.stop()
            self._is_running = False
            logger.info("Alert bot stopped")
    
    # Command Handlers
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🔔 *Alert Bot*\n\n"
            "This bot sends system alerts and notifications.\n"
            "Use /status for current system status.",
            parse_mode='Markdown'
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        from system.health import get_health_checker
        from system.self_defense import get_self_defense
        from system.metrics import get_metrics_collector
        
        health = await get_health_checker().get_health_summary()
        self_defense = await get_self_defense().get_safe_mode_status()
        metrics = await get_metrics_collector().get_all_metrics_summary()
        
        message = (
            f"📊 *System Status*\n\n"
            f"*Health:* {health.get('status', 'unknown').upper()}\n"
            f"*Safe Mode:* {self_defense.get('state', 'normal').upper()}\n"
            f"*Uptime:* {metrics.get('uptime_formatted', 'N/A')}\n\n"
            f"*Tracked Metrics:* {metrics.get('tracked_metrics', 0)}\n"
        )
        
        await update.message.reply_text(
            message,
            parse_mode='Markdown'
        )
    
    # Alert Methods
    
    async def send_system_alert(
        self,
        title: str,
        message: str,
        severity: str = "info",
        notify_admin: bool = False
    ):
        """Send a system alert"""
        
        if not self.application or not self._is_running:
            logger.warning("Alert bot not running, cannot send alert")
            return
        
        # Severity formatting
        severity_emojis = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '❌',
            'critical': '🚨'
        }
        
        emoji = severity_emojis.get(severity, 'ℹ️')
        
        full_message = f"{emoji} *{title}*\n\n{message}"
        
        try:
            # Send to main alert channel
            await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=full_message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            # Send to admin if critical
            if notify_admin and severity == 'critical' and self.admin_chat_id:
                await self.application.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=f"🚨 *ADMIN ALERT* 🚨\n\n{full_message}",
                    parse_mode='Markdown'
                )
            
            logger.debug(f"System alert sent: {title}")
        
        except Exception as e:
            logger.error(f"Failed to send system alert: {e}")
    
    async def send_failure_alert(
        self,
        component: str,
        error: str,
        details: Optional[str] = None
    ):
        """Send component failure alert"""
        
        message = (
            f"❌ *Component Failure*\n\n"
            f"*Component:* {component}\n"
            f"*Error:* `{error}`\n"
        )
        
        if details:
            message += f"\n*Details:*\n{details}"
        
        await self.send_system_alert(
            title="SYSTEM FAILURE",
            message=message,
            severity='error',
            notify_admin=True
        )
    
    async def send_self_defense_alert(
        self,
        reason: str,
        metrics: dict,
        actions_taken: list
    ):
        """Send self-defense activation alert"""
        
        message = (
            f"🛡️ *SAFE MODE ACTIVATED* 🛡️\n\n"
            f"*Reason:* {reason}\n\n"
            f"*Current Metrics:*\n"
            f"• API Error Rate: {metrics.get('api_error_rate', 0):.1%}\n"
            f"• Avg Latency: {metrics.get('avg_latency_ms', 0):.0f}ms\n"
            f"• Memory: {metrics.get('memory_usage_mb', 0):.0f}MB\n"
            f"• CPU: {metrics.get('cpu_usage_percent', 0):.1f}%\n\n"
            f"*Actions Taken:*\n"
        )
        
        for action in actions_taken:
            message += f"• {action}\n"
        
        await self.send_system_alert(
            title="SELF-DEFENSE ACTIVATED",
            message=message,
            severity='critical',
            notify_admin=True
        )
    
    async def send_escalation_alert(
        self,
        alert_type: str,
        description: str,
        severity: str,
        metrics: dict
    ):
        """Send escalation alert"""
        
        message = (
            f"⚠️ *ESCALATION ALERT* ⚠️\n\n"
            f"*Type:* {alert_type}\n"
            f"*Severity:* {severity.upper()}\n\n"
            f"*Description:*\n{description}\n\n"
            f"*Metrics:*\n"
        )
        
        for key, value in metrics.items():
            message += f"• {key}: {value}\n"
        
        await self.send_system_alert(
            title="ESCALATION",
            message=message,
            severity='warning' if severity == 'medium' else 'error',
            notify_admin=(severity == 'critical')
        )
    
    async def send_recovery_alert(
        self,
        component: str,
        recovery_time_seconds: int
    ):
        """Send recovery notification"""
        
        message = (
            f"✅ *Recovery Complete*\n\n"
            f"*Component:* {component}\n"
            f"*Recovery Time:* {format_duration(recovery_time_seconds)}\n\n"
            f"System has returned to normal operation."
        )
        
        await self.send_system_alert(
            title="SYSTEM RECOVERED",
            message=message,
            severity='info'
        )
    
    async def send_daily_summary(
        self,
        stats: dict
    ):
        """Send daily summary"""
        
        message = (
            f"📈 *Daily Summary*\n\n"
            f"*Tokens Processed:* {stats.get('tokens_processed', 0)}\n"
            f"*Alerts Generated:* {stats.get('alerts_generated', 0)}\n"
            f"*Watches Triggered:* {stats.get('watches_triggered', 0)}\n"
            f"*Exit Signals:* {stats.get('exit_signals', 0)}\n\n"
            f"*System Health:* {stats.get('health_status', 'unknown')}\n"
            f"*Uptime:* {stats.get('uptime_formatted', 'N/A')}\n"
        )
        
        await self.send_system_alert(
            title="DAILY SUMMARY",
            message=message,
            severity='info'
        )
    
    async def send_startup_notification(self):
        """Send startup notification"""
        
        message = (
            f"🚀 *System Started*\n\n"
            f"*Timestamp:* {get_timestamp()}\n"
            f"*Version:* 1.0.0\n\n"
            f"All systems initializing..."
        )
        
        await self.send_system_alert(
            title="SYSTEM STARTUP",
            message=message,
            severity='info'
        )
    
    async def send_shutdown_notification(self, reason: str = "manual"):
        """Send shutdown notification"""
        
        message = (
            f"🛑 *System Shutdown*\n\n"
            f"*Reason:* {reason}\n"
            f"*Timestamp:* {get_timestamp()}\n"
        )
        
        await self.send_system_alert(
            title="SYSTEM SHUTDOWN",
            message=message,
            severity='warning'
        )


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_alert_bot: Optional[AlertBot] = None


def get_alert_bot() -> AlertBot:
    """Get or create alert bot singleton"""
    global _alert_bot
    if _alert_bot is None:
        _alert_bot = AlertBot()
    return _alert_bot
