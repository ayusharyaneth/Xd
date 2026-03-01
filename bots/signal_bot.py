from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config.settings import settings
from system.health import health_monitor
from system.self_defense import self_defense
from engines.regime import regime_analyzer
from watch.watch_manager import watch_manager
from utils.logger import logger
from datetime import datetime

class SignalBot:
    def __init__(self):
        self.app = Application.builder().token(settings.SIGNAL_BOT_TOKEN).build()
        self.chat_id = settings.SIGNAL_CHAT_ID

        # Register handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("ping", self.ping))
        self.app.add_handler(CommandHandler("watch", self.watch_list))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome message with control buttons"""
        welcome_text = (
            "🤖 **Welcome to DexScreener Intelligence Bot**\n\n"
            "I'll monitor new token listings and send you high-quality alpha signals.\n"
            "Use the buttons below or type /help for more commands.\n\n"
            "⚡ *Features:*\n"
            "• Smart risk filtering\n"
            "• Whale detection\n"
            "• Watchlist management\n"
            "• Auto exit alerts"
        )

        keyboard = [
            [
                InlineKeyboardButton("📋 My Watchlist", callback_data="show_watchlist"),
                InlineKeyboardButton("🏓 System Status", callback_data="show_status")
            ],
            [
                InlineKeyboardButton("❓ Help", callback_data="show_help"),
                InlineKeyboardButton("🔄 Refresh Data", callback_data="refresh_all")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information"""
        help_text = (
            "📚 **Available Commands:**\n\n"
            "/start - Initialize bot and show menu\n"
            "/watch - View your current watchlist\n"
            "/ping - Check system health and metrics\n"
            "/help - Show this help message\n\n"
            "**How it works:**\n"
            "1. I scan DexScreener for new tokens\n"
            "2. High-quality tokens get 'Alpha Detected' alerts\n"
            "3. Click '👁 Watch' to add to your watchlist\n"
            "4. I'll send updates only for your watched tokens\n"
            "5. Exit alerts trigger when risk increases"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def watch_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display current watchlist"""
        # Get watchlist from manager
        watches = list(watch_manager.watched_tokens.items())

        if not watches:
            await update.message.reply_text(
                "👁 **Your Watchlist is empty**\n\n"
                "Add tokens by clicking the '👁 Watch' button on alpha alerts.",
                parse_mode="Markdown"
            )
            return

        message = "👁 **Your Watchlist:**\n\n"
        keyboard = []

        for i, (address, item) in enumerate(watches, 1):
            symbol = item.get("baseToken", {}).get("symbol", "Unknown")
            price = item.get("priceUsd", "0")
            short_addr = address[:6] + "..." + address[-4:]
            message += f"{i}. **{symbol}** | ${price}\n   `{short_addr}`\n\n"
            keyboard.append([InlineKeyboardButton(
                f"❌ Remove {symbol}",
                callback_data=f"remove|{address}"
            )])

        keyboard.append([InlineKeyboardButton("🔄 Refresh All", callback_data="refresh_all_watches")])

        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced status command"""
        health = health_monitor.get_system_health()
        regime = regime_analyzer.current_regime
        sm_state = "🟢 INACTIVE" if not self_defense.is_safe_mode() else "🔴 ACTIVE"
        watch_count = watch_manager.get_count()
        status_icon = "🟢" if health.get('healthy', False) else "🔴"

        msg = (
            f"{status_icon} **System Status Report**\n\n"
            f"**Health Metrics:**\n"
            f"• Status: {'Healthy' if health.get('healthy') else 'Degraded'}\n"
            f"• Latency: {health.get('avg_latency_ms', 0):.2f}ms\n"
            f"• CPU Usage: {health.get('cpu_percent', 0)}%\n"
            f"• Memory: {health.get('memory_percent', 0):.1f}%\n"
            f"• Error Rate: {health.get('error_rate', 0):.2%}\n\n"
            f"**Operational Status:**\n"
            f"• Market Regime: {regime}\n"
            f"• Safe Mode: {sm_state}\n"
            f"• Active Watches: {watch_count}\n"
            f"• Chat ID: {self.chat_id}"
        )

        keyboard = [[InlineKeyboardButton("🔄 Refresh Status", callback_data="show_status")]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    async def send_signal(self, pair_data: dict, score: float, is_update: bool = False):
        """Send signal to Telegram"""
        try:
            symbol = pair_data.get("baseToken", {}).get("symbol", "UNKNOWN")
            address = pair_data.get("baseToken", {}).get("address", "UNKNOWN")
            price = pair_data.get("priceUsd", "0")
            fdv = pair_data.get("fdv", 0)
            liquidity = pair_data.get("liquidity", {}).get("usd", 0)

            header = "🔄 **WATCHLIST UPDATE**" if is_update else "🚀 **NEW ALPHA DETECTED**"
            footer = "ℹ️ Update for watched token" if is_update else "⚡ High quality signal"

            msg = (
                f"{header}\n\n"
                f"**Token:** {symbol}\n"
                f"**Address:** `{address}`\n"
                f"**Price:** ${price}\n"
                f"**FDV:** ${fdv:,.0f}\n"
                f"**Liquidity:** ${liquidity:,.0f}\n"
                f"**Quality Score:** {score:.1f}/100\n\n"
                f"{footer}"
            )

            if is_update:
                keyboard = [[
                    InlineKeyboardButton("📊 Details", callback_data=f"details|{address}"),
                    InlineKeyboardButton("❌ Unwatch", callback_data=f"unwatch|{address}")
                ]]
            else:
                keyboard = [[
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh|{address}"),
                    InlineKeyboardButton("👁 Watch", callback_data=f"watch|{address}")
                ]]

            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Failed to send signal: {e}")

    async def send_watch_alert(self, token_address: str, reason: str):
        """Send exit/escalation alert"""
        try:
            token_data = watch_manager.watched_tokens.get(token_address, {})
            symbol = token_data.get("baseToken", {}).get("symbol", "UNKNOWN")

            msg = (
                f"⚠️ **WATCHLIST ALERT** ⚠️\n\n"
                f"**Token:** {symbol}\n"
                f"**Address:** `{token_address}`\n"
                f"**Alert:** {reason}\n\n"
                f"🔴 **Action Required:** Consider exiting position."
            )

            keyboard = [[
                InlineKeyboardButton("📋 View Details", callback_data=f"details|{token_address}"),
                InlineKeyboardButton("❌ Remove", callback_data=f"unwatch|{token_address}")
            ]]

            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send watch alert: {e}")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        data = query.data

        try:
            if data == "show_watchlist":
                await self.watch_list(update, context)
            elif data == "show_status":
                await self.ping(update, context)
            elif data == "show_help":
                await self.help_command(update, context)
            elif data == "refresh_all" or data == "refresh_all_watches":
                await query.edit_message_text(f"{query.message.text}\n\n_🔄 Refreshing..._", parse_mode="Markdown")
            elif data.startswith("watch|"):
                address = data.split("|")[1]
                watch_manager.add_watch(address, {"baseToken": {"symbol": "Unknown", "address": address}})
                await query.edit_message_text(f"{query.message.text}\n\n✅ *Added to Watchlist!*", parse_mode="Markdown")
            elif data.startswith(("unwatch|", "remove|")):
                address = data.split("|")[1]
                watch_manager.remove_watch(address)
                await query.edit_message_text(f"{query.message.text}\n\n❌ *Removed*", parse_mode="Markdown")
            elif data.startswith("refresh|"):
                await query.edit_message_text(f"{query.message.text}\n\n_🔄 Refreshed at {datetime.now().strftime('%H:%M:%S')}_", parse_mode="Markdown")
            elif data.startswith("details|"):
                address = data.split("|")[1]
                await query.answer("Monitoring active", show_alert=True)
        except Exception as e:
            logger.error(f"Button handler error: {e}")
            await query.answer("Error processing request", show_alert=True)

    async def start_bot(self):
        """Start the signal bot - v20+ compatible polling"""
        self._polling_task = asyncio.create_task(
            self.app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        )
        logger.info("Signal Bot started and polling")

    async def stop_bot(self):
        """Graceful shutdown"""
        try:
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Signal Bot stopped")
        except Exception as e:
            logger.error(f"Error stopping signal bot: {e}")

import asyncio
signal_bot = SignalBot()
