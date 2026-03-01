from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config.settings import settings
from utils.logger import log
from utils.state import state_manager
from api.dexscreener import DexScreenerAPI
import asyncio

class SignalBot:
    def __init__(self, api: DexScreenerAPI):
        self.api = api
        self.app = Application.builder().token(settings.SIGNAL_BOT_TOKEN).build()
        self._setup_handlers()

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("ping", self.cmd_ping))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    async def initialize(self):
        await self.app.initialize()
        await self.app.start()
        # Non-blocking polling
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🤖 DexScreener Intelligence Bot Active")

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        watches = len(state_manager.get_all())
        await update.message.reply_text(f"🏓 Pong!\nWatching {watches} tokens.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        # CRITICAL: Always answer query to stop loading animation
        await query.answer()
        
        data = query.data.split(":")
        action = data[0]
        address = data[1] if len(data) > 1 else None

        if action == "watch" and address:
            # We need to fetch current price for entry
            try:
                pairs = await self.api.get_pairs_bulk([address])
                if pairs:
                    price = float(pairs[0].get('priceUsd', 0))
                    metadata = {
                        "entry_price": price,
                        "symbol": pairs[0]['baseToken']['symbol'],
                        "chat_id": query.message.chat_id
                    }
                    await state_manager.add_token(address, metadata)
                    await query.edit_message_caption(
                        caption=query.message.caption + f"\n\n✅ **Added to Watchlist @ ${price}**",
                        reply_markup=query.message.reply_markup
                    )
            except Exception as e:
                log.error(f"Watch error: {e}")

    async def broadcast_signal(self, analysis: dict):
        """Sends the formatted signal to the channel"""
        msg = (
            f"💎 **GEM DETECTED: {analysis['baseToken']['name']}**\n"
            f"Symbol: ${analysis['baseToken']['symbol']}\n"
            f"Address: `{analysis['address']}`\n\n"
            f"💰 Price: ${analysis['priceUsd']}\n"
            f"💧 Liquidity: ${analysis['liquidity']:,.0f}\n"
            f"📊 Risk Score: {analysis['risk']['score']}/100\n"
            f"🐋 Whale: {'YES 🚨' if analysis['whale']['detected'] else 'No'}\n"
        )
        
        keyboard = [[
            InlineKeyboardButton("👁 Watch", callback_data=f"watch:{analysis['address']}"),
            InlineKeyboardButton("📈 DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{analysis['address']}")
        ]]

        try:
            await self.app.bot.send_message(
                chat_id=settings.CHANNEL_ID,
                text=msg,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            log.error(f"Broadcast failed: {e}")

    async def send_exit_alert(self, address: str, pnl: float, reason: str):
        # Notify admins or specific chat
        data = state_manager.get_all().get(address)
        if not data: return
        
        msg = f"🔔 **EXIT SIGNAL**\n{data['symbol']}: {reason}\nPnL: {pnl:.2f}%"
        try:
            await self.app.bot.send_message(chat_id=data['chat_id'], text=msg)
        except Exception as e:
            log.error(f"Exit alert failed: {e}")

    async def shutdown(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
