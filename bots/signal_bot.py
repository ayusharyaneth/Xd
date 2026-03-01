# ============================================================
# SIGNAL BOT - Telegram Bot for Intelligence Alerts
# ============================================================

import asyncio
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import (
    get_timestamp, format_currency, format_percentage,
    escape_markdown, shorten_address
)
from watch.watch_manager import get_watch_manager
from system.health import get_health_checker
from system.self_defense import get_self_defense
from engines.regime import get_regime_analyzer


logger = get_logger("signal_bot")


class SignalBot:
    """Telegram bot for sending intelligence signals"""
    
    def __init__(self):
        self.config = get_config()
        self.token = self.config.settings.SIGNAL_BOT_TOKEN
        self.chat_id = self.config.settings.SIGNAL_CHAT_ID
        self.application: Optional[Application] = None
        self._is_running = False
    
    async def initialize(self):
        """Initialize the bot"""
        if not self.token:
            logger.error("Signal bot token not configured")
            return False
        
        try:
            self.application = Application.builder().token(self.token).build()
            
            # Add handlers
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("ping", self.cmd_ping))
            self.application.add_handler(CommandHandler("watchlist", self.cmd_watchlist))
            self.application.add_handler(CommandHandler("regime", self.cmd_regime))
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))
            
            await self.application.initialize()
            await self.application.start()
            
            self._is_running = True
            logger.info("Signal bot initialized")
            return True
        
        except Exception as e:
            logger.error(f"Failed to initialize signal bot: {e}")
            return False
    
    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.stop()
            self._is_running = False
            logger.info("Signal bot stopped")
    
    # Command Handlers
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = (
            "🤖 *DexScreener Intelligence Bot*\n\n"
            "Welcome! I'm your crypto intelligence assistant.\n\n"
            "*Commands:*\n"
            "• /ping - System status\n"
            "• /watchlist - View watched tokens\n"
            "• /regime - Current market regime\n\n"
            "I'll send you intelligence-rich alerts for new tokens!"
        )
        
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown'
        )
    
    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ping command"""
        
        start_time = get_timestamp()
        
        # Gather system status
        health = await get_health_checker().get_health_summary()
        self_defense = await get_self_defense().get_safe_mode_status()
        regime = await get_regime_analyzer().get_regime_summary()
        watch_manager = get_watch_manager()
        watches = await watch_manager.get_all_watches_summary()
        
        response_time = get_timestamp() - start_time
        
        status_emoji = "🟢" if health.get('status') == 'healthy' else "🟡" if health.get('status') == 'warning' else "🔴"
        safe_mode_emoji = "🛡️" if self_defense.get('in_safe_mode') else "✅"
        
        message = (
            f"{status_emoji} *System Status*\n\n"
            f"*Health:* {health.get('status', 'unknown').upper()}\n"
            f"*Response Time:* {response_time}ms\n"
            f"*Safe Mode:* {safe_mode_emoji} {self_defense.get('state', 'unknown')}\n"
            f"*Market Regime:* {regime.get('regime', 'unknown').upper()}\n"
            f"*Active Watches:* {watches.get('total_watches', 0)}\n\n"
            f"*Regime Message:* {regime.get('message', 'N/A')}\n\n"
            f"_Bot is operational_"
        )
        
        await update.message.reply_text(
            message,
            parse_mode='Markdown'
        )
    
    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /watchlist command"""
        
        watch_manager = get_watch_manager()
        watches = await watch_manager.get_all_watches_summary()
        
        if watches.get('total_watches', 0) == 0:
            await update.message.reply_text(
                "📭 *Watch List Empty*\n\n"
                "No tokens are currently being watched.\n"
                "Use the 👁 Watch button on alerts to add tokens.",
                parse_mode='Markdown'
            )
            return
        
        message = (
            f"👁 *Active Watches: {watches['total_watches']}*\n\n"
            f"🟢 Active: {watches['active']}\n"
            f"🔴 Escalated: {watches['escalated']}\n"
            f"📈 Price Up >20%: {watches['price_up_significant']}\n"
            f"📉 Price Down >20%: {watches['price_down_significant']}\n\n"
        )
        
        # Add watch details
        for watch in watches.get('watches', [])[:5]:
            emoji = "🟢" if watch['price_change'] > 0 else "🔴"
            message += (
                f"{emoji} *{watch['symbol']}*\n"
                f"   Price: {watch['price_change']:+.1f}% | "
                f"Expires: {watch['expires_in']}\n\n"
            )
        
        await update.message.reply_text(
            message,
            parse_mode='Markdown'
        )
    
    async def cmd_regime(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /regime command"""
        
        regime = await get_regime_analyzer().get_regime_summary()
        
        regime_emojis = {
            'bull': '🐂',
            'bear': '🐻',
            'chop': '⚖️',
            'volatile': '📊',
            'unknown': '❓'
        }
        
        emoji = regime_emojis.get(regime.get('regime'), '❓')
        
        message = (
            f"{emoji} *Market Regime: {regime.get('regime', 'unknown').upper()}*\n\n"
            f"*Confidence:* {regime.get('confidence', 0):.0%}\n"
            f"*Duration:* {regime.get('duration_minutes', 0)} minutes\n\n"
            f"*Indicators:*\n"
        )
        
        indicators = regime.get('indicators', {})
        for key, value in indicators.items():
            message += f"• {key.replace('_', ' ').title()}: {value}\n"
        
        message += f"\n💡 *Advice:* {regime.get('message', 'Monitor market conditions')}"
        
        await update.message.reply_text(
            message,
            parse_mode='Markdown'
        )
    
    # Callback Handler
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("refresh:"):
            token_address = data.split(":")[1]
            await self._handle_refresh(query, token_address)
        
        elif data.startswith("watch:"):
            parts = data.split(":")
            token_address = parts[1]
            token_symbol = parts[2] if len(parts) > 2 else "Unknown"
            await self._handle_watch(query, token_address, token_symbol)
        
        elif data == "ping":
            await self._handle_ping_callback(query)
    
    async def _handle_refresh(self, query, token_address: str):
        """Handle refresh button"""
        await query.edit_message_text(
            f"🔄 Refreshing data for token...\n`{shorten_address(token_address)}`",
            parse_mode='Markdown'
        )
    
    async def _handle_watch(
        self,
        query,
        token_address: str,
        token_symbol: str
    ):
        """Handle watch button"""
        
        watch_manager = get_watch_manager()
        
        # Create minimal pair info
        from api.dexscreener import TokenPair
        pair = TokenPair(
            chain_id="unknown",
            dex_id="unknown",
            pair_address="",
            token_address=token_address,
            token_name=token_symbol,
            token_symbol=token_symbol
        )
        
        watch = await watch_manager.add_watch(
            pair=pair,
            added_by=query.from_user.username or str(query.from_user.id)
        )
        
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"👁 *Added to Watch List*\n\n"
            f"Token: *{token_symbol}*\n"
            f"Watching for: 30 minutes\n\n"
            f"Use /watchlist to see all watched tokens.",
            parse_mode='Markdown'
        )
    
    async def _handle_ping_callback(self, query):
        """Handle ping button callback"""
        await query.edit_message_text(
            "🏓 Pong! Bot is responsive.",
            parse_mode='Markdown'
        )
    
    # Alert Methods
    
    async def send_alert(
        self,
        title: str,
        message: str,
        token_address: Optional[str] = None,
        token_symbol: Optional[str] = None,
        severity: str = "info",
        include_buttons: bool = True
    ):
        """Send an alert message"""
        
        if not self.application or not self._is_running:
            logger.warning("Signal bot not running, cannot send alert")
            return
        
        # Severity emoji
        severity_emojis = {
            'info': 'ℹ️',
            'low': '🟢',
            'medium': '🟡',
            'high': '🔴',
            'critical': '🚨'
        }
        
        emoji = severity_emojis.get(severity, 'ℹ️')
        
        full_message = f"{emoji} *{title}*\n\n{message}"
        
        # Build keyboard
        keyboard = []
        if include_buttons and token_address:
            keyboard.append([
                InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data=f"refresh:{token_address}"
                ),
                InlineKeyboardButton(
                    "👁 Watch",
                    callback_data=f"watch:{token_address}:{token_symbol or 'Unknown'}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        try:
            await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=full_message,
                parse_mode='Markdown',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            logger.debug(f"Alert sent: {title}")
        
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    async def send_token_alert(
        self,
        pair,
        risk_score: float,
        volume_score: float,
        composite_score: float,
        analysis: Dict[str, Any]
    ):
        """Send token opportunity alert"""
        
        # Determine severity based on composite score
        if composite_score >= 80:
            severity = 'high'
        elif composite_score >= 65:
            severity = 'medium'
        else:
            severity = 'low'
        
        # Format message
        message = (
            f"🪙 *{escape_markdown(pair.token_symbol)}*\n"
            f"`{shorten_address(pair.token_address)}`\n\n"
            f"💰 *Price:* ${pair.price_usd:.8f}\n"
            f"📊 *24h Change:* {format_percentage(pair.price_change_24h)}\n"
            f"💧 *Liquidity:* {format_currency(pair.liquidity_usd)}\n"
            f"📈 *Volume 24h:* {format_currency(pair.volume_24h)}\n"
            f"🏦 *Market Cap:* {format_currency(pair.market_cap)}\n\n"
            f"*Scores:*\n"
            f"• Composite: {composite_score:.0f}/100\n"
            f"• Risk: {risk_score:.0f}/100\n"
            f"• Volume Quality: {volume_score:.0f}/100\n\n"
        )
        
        # Add analysis points
        if analysis.get('key_points'):
            message += "*Key Points:*\n"
            for point in analysis['key_points'][:5]:
                message += f"• {escape_markdown(point)}\n"
        
        await self.send_alert(
            title="NEW TOKEN ALERT",
            message=message,
            token_address=pair.token_address,
            token_symbol=pair.token_symbol,
            severity=severity
        )
    
    async def send_exit_alert(self, exit_signal):
        """Send exit recommendation alert"""
        
        urgency_emojis = {
            'low': '🟡',
            'medium': '🟠',
            'high': '🔴',
            'critical': '🚨'
        }
        
        emoji = urgency_emojis.get(exit_signal.urgency.value, '🟡')
        
        message = (
            f"{emoji} *EXIT ALERT* {emoji}\n\n"
            f"Token: `{shorten_address(exit_signal.token_address)}`\n"
            f"Trigger: {exit_signal.trigger_type.value.replace('_', ' ').title()}\n"
            f"Urgency: {exit_signal.urgency.value.upper()}\n\n"
            f"Current Price: ${exit_signal.current_price:.8f}\n"
        )
        
        if exit_signal.current_pnl is not None:
            pnl_emoji = "🟢" if exit_signal.current_pnl > 0 else "🔴"
            message += f"Current PnL: {pnl_emoji} {exit_signal.current_pnl:+.1f}%\n"
        
        message += f"\n*Recommendation:* {exit_signal.recommendation}\n\n"
        message += "*Rationale:*\n"
        for rationale in exit_signal.rationale:
            message += f"• {escape_markdown(rationale)}\n"
        
        await self.send_alert(
            title="EXIT RECOMMENDATION",
            message=message,
            token_address=exit_signal.token_address,
            severity=exit_signal.urgency.value
        )
    
    async def send_watch_update(self, watch, alert: Optional[str] = None):
        """Send watch mode update"""
        
        emoji = "🚨" if alert else "👁"
        
        message = (
            f"{emoji} *Watch Update: {watch.token_symbol}*\n\n"
            f"Price Change: {watch.price_change_percent:+.1f}%\n"
            f"Volume Change: {watch.volume_change_percent:+.1f}%\n"
            f"Risk Change: {watch.risk_change:+.0f}\n"
        )
        
        if alert:
            message += f"\n⚠️ *Alert:* {alert}"
        
        await self.send_alert(
            title="WATCH UPDATE",
            message=message,
            token_address=watch.token_address,
            severity='medium' if alert else 'low',
            include_buttons=True
        )


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_signal_bot: Optional[SignalBot] = None


def get_signal_bot() -> SignalBot:
    """Get or create signal bot singleton"""
    global _signal_bot
    if _signal_bot is None:
        _signal_bot = SignalBot()
    return _signal_bot
