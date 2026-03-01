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
        """
        Initializes the bot application and starts the polling mechanism 
        in a non-blocking background task.
        """
        await self.app.initialize()
        await self.app.start()
        # drop_pending_updates=True ensures the bot doesn't crash processing old/stale updates on startup
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        log.info("Signal Bot Polling Started")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handles /start command. Displays welcome message and status button.
        """
        keyboard = [
            [InlineKeyboardButton("🟢 Online", callback_data="status_check")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 **DexScreener Intelligence System**\n\n"
            "System is active and monitoring the blockchain for high-value signals.\n"
            "You will receive automatic alerts in the configured channel.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        watches = len(state_manager.get_all())
        await update.message.reply_text(f"🏓 Pong!\nWatching {watches} tokens.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Central router for all inline button clicks.
        """
        query = update.callback_query
        # Always answer to stop the loading animation on the client side
        await query.answer()
        
        data = query.data.split(":")
        action = data[0]
        
        try:
            if action == "status_check":
                await query.edit_message_text(
                    text=f"✅ **System Normal**\nTime: {asyncio.get_running_loop().time():.2f}",
                    parse_mode='Markdown'
                )
                
            elif action == "watch":
                address = data[1] if len(data) > 1 else None
                if address:
                    await self._handle_watch_action(query, address)
                    
            elif action == "refresh":
                # Placeholder for refresh logic - typically re-fetches token data
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n🔄 *Data Refreshed*",
                    parse_mode='Markdown',
                    reply_markup=query.message.reply_markup
                )

        except Exception as e:
            log.error(f"Callback error ({action}): {e}")

    async def _handle_watch_action(self, query, address):
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
                
                # Update the button to show it's being watched
                keyboard = [
                    [InlineKeyboardButton("✅ Watching", callback_data="noop")],
                    [InlineKeyboardButton("📈 DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{address}")]
                ]
                
                await query.edit_message_caption(
                    caption=query.message.caption + f"\n\n✅ **Added to Watchlist @ ${price}**",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except Exception as e:
            log.error(f"Watch action failed: {e}")

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
        data = state_manager.get_all().get(address)
        if not data: return
        
        msg = f"🔔 **EXIT SIGNAL**\n{data['symbol']}: {reason}\nPnL: {pnl:.2f}%"
        try:
            await self.app.bot.send_message(chat_id=data['chat_id'], text=msg)
        except Exception as e:
            log.error(f"Exit alert failed: {e}")

    async def shutdown(self):
        if self.app.updater.running:
            await self.app.updater.stop()
        if self.app.running:
            await self.app.stop()
        await self.app.shutdown()
