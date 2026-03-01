from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config.settings import settings
from loguru import logger
from watch.watch_manager import watch_manager
from system.health import SystemHealth
from system.self_defense import SelfDefense
import asyncio

class SignalBot:
    def __init__(self, defense_sys: SelfDefense):
        self.app = Application.builder().token(settings.env.SIGNAL_BOT_TOKEN).build()
        self.defense_sys = defense_sys
        self.health_sys = SystemHealth()
        
    def setup_handlers(self):
        self.app.add_handler(CommandHandler("ping", self.ping_command))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    async def initialize(self):
        self.setup_handlers()
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        metrics = self.health_sys.get_metrics()
        safe_mode = self.defense_sys.safe_mode
        watches = len(watch_manager.get_active_watches())
        
        msg = (
            f"🏓 **PONG**\n\n"
            f"🟢 System Status: {'SAFE MODE' if safe_mode else 'NORMAL'}\n"
            f"💻 CPU: {metrics['cpu']}%\n"
            f"💾 RAM: {metrics['ram']}%\n"
            f"👁 Active Watches: {watches}\n"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data.split(":")
        action = data[0]
        token = data[1] if len(data) > 1 else None
        
        if action == "watch" and token:
            # Mock entry price fetch for simplicity, usually passed in query or fetched
            watch_manager.add_watch(token, query.message.chat_id, 0.0)
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n✅ **Added to Watchlist**")
        
        elif action == "refresh":
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n🔄 **Refreshed (Mock)**")

    async def send_signal(self, token_data, analysis):
        msg = self._format_message(token_data, analysis)
        keyboard = [
            [
                InlineKeyboardButton("👁 Watch", callback_data=f"watch:{token_data['pairAddress']}"),
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh:{token_data['pairAddress']}")
            ],
            [InlineKeyboardButton("DexScreener", url=token_data['url'])]
        ]
        
        try:
            await self.app.bot.send_message(
                chat_id=settings.env.CHANNEL_ID, 
                text=msg, 
                parse_mode='Markdown', 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Failed to send signal: {e}")

    def _format_message(self, data, analysis):
        # Construct rich message
        return (
            f"🚨 **NEW GEM DETECTED** 🚨\n\n"
            f"💎 **{data['baseToken']['name']}** ({data['baseToken']['symbol']})\n"
            f"📜 `{data['pairAddress']}`\n\n"
            f"📊 **Score:** {analysis['score']}/100\n"
            f"🐋 **Whale Alert:** {'YES' if analysis['whale'] else 'No'}\n"
            f"⚠️ **Risk:** {analysis['risk_score']}\n"
            f"💰 **Liq:** ${data.get('liquidity',{}).get('usd',0)}\n"
        )

    async def shutdown(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
