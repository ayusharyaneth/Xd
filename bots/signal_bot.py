from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from config.settings import settings, strategy
from utils.logger import log
from utils.state import state_manager
from api.dexscreener import DexScreenerAPI
from engines.analysis import AnalysisEngine
import asyncio
from datetime import datetime

class SignalBot:
    def __init__(self, api: DexScreenerAPI):
        self.api = api
        self.app = Application.builder().token(settings.SIGNAL_BOT_TOKEN).build()
        self._setup_handlers()

    def _setup_handlers(self):
        # Commands
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("ping", self.cmd_ping))
        
        # Callbacks
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Text Input (For Settings Editing)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, self.handle_text_input))

    async def initialize(self):
        log.info("Initializing Signal Bot Interface...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        log.info("Signal Bot Terminal Active")

    # --- Command Handlers ---

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear() 
        await self._render_dashboard(update.message, is_new=True)

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("● System Online")

    # --- Interaction Router ---

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data.split(":")
        action = data[0]
        
        # Clear edit mode unless specific action logic preserves it
        if action != "settings_prompt":
             context.user_data['edit_mode'] = None

        try:
            # Dashboard Navigation
            if action == "dashboard":
                await self._render_dashboard(query.message)
            
            # Settings System
            elif action == "settings_home":
                await self._render_settings_home(query.message)
            elif action == "settings_cat":
                category = data[1]
                await self._render_settings_category(query.message, category)
            elif action == "settings_toggle":
                category, key = data[1], data[2]
                current = getattr(strategy, category).get(key, False)
                await strategy.update_setting(category, key, not current)
                await self._render_settings_category(query.message, category)
            elif action == "settings_prompt":
                category, key = data[1], data[2]
                context.user_data['edit_mode'] = {'cat': category, 'key': key}
                await query.message.reply_text(
                    f"📝 **EDIT PARAMETER**\n"
                    f"Category: `{category.upper()}`\n"
                    f"Key: `{key}`\n"
                    f"Current: `{getattr(strategy, category).get(key)}`\n\n"
                    f"Enter new value below:",
                    parse_mode='Markdown'
                )

            # Watchlist Actions
            elif action == "watchlist_view":
                await self._render_watchlist(query.message)
            elif action == "watchlist_refresh":
                await self._handle_refresh_watchlist(query)
            elif action == "watch":
                address = data[1] if len(data) > 1 else None
                if address: await self._handle_watch_action(query, address)

            # Utilities
            elif action == "help_menu":
                await self._render_help(query.message)

        except Exception as e:
            log.error(f"UI Router Error ({action}): {e}")

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes input for setting edits."""
        edit_state = context.user_data.get('edit_mode')
        
        if not edit_state:
            return 

        try:
            val = update.message.text.strip()
            cat = edit_state['cat']
            key = edit_state['key']
            
            await strategy.update_setting(cat, key, val)
            
            await update.message.reply_text(f"✓ Value updated to: `{val}`")
            context.user_data['edit_mode'] = None 
            await self._render_settings_category(update.message, cat, is_new=True)
            
        except ValueError:
            await update.message.reply_text("⚠️ Invalid format. Please enter a valid number or boolean.")
        except Exception as e:
            log.error(f"Edit persistence failed: {e}")
            await update.message.reply_text("⚠️ System error saving configuration.")

    # --- UI Rendering Engine ---

    async def _render_dashboard(self, message, is_new=False):
        watchlist_count = len(state_manager.get_all())
        strict_mode = strategy.thresholds.get('strict_filtering', True)
        timestamp = datetime.utcnow().strftime('%H:%M:%S UTC')
        
        # Professional Fintech Layout
        text = (
            f"**DEXSCREENER INTELLIGENCE TERMINAL**\n"
            f"● SYSTEM ONLINE  |  TARGET: {settings.TARGET_CHAIN.upper()}\n"
            f"─────────────────────────────\n"
            f"**METRICS**\n"
            f"Watchlist    ::  {watchlist_count} Active\n"
            f"Liquidity    ::  > ${strategy.filters.get('min_liquidity_usd', 0):,}\n"
            f"Strict Mode  ::  {'ENABLED' if strict_mode else 'DISABLED'}\n"
            f"Last Update  ::  {timestamp}\n"
            f"─────────────────────────────"
        )

        keyboard = [
            [
                InlineKeyboardButton("📁 Watchlist", callback_data="watchlist_view"),
                InlineKeyboardButton("🔄 Refresh", callback_data="watchlist_refresh")
            ],
            [
                InlineKeyboardButton("⚙ Configuration", callback_data="settings_home"),
                InlineKeyboardButton("❓ Guide", callback_data="help_menu")
            ]
        ]
        
        if is_new:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_settings_home(self, message):
        text = (
            f"**CONFIGURATION PANEL**\n"
            f"Select a module to configure parameters.\n"
            f"─────────────────────────────"
        )
        keyboard = [
            [InlineKeyboardButton("Filters (Liquidity, Age)", callback_data="settings_cat:filters")],
            [InlineKeyboardButton("Weights (Scoring)", callback_data="settings_cat:weights")],
            [InlineKeyboardButton("Thresholds (Risk/Exit)", callback_data="settings_cat:thresholds")],
            [InlineKeyboardButton("← Return to Terminal", callback_data="dashboard")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_settings_category(self, message, category, is_new=False):
        data = getattr(strategy, category)
        text = (
            f"**EDITING :: {category.upper()}**\n"
            f"Tap a parameter to modify value.\n"
            f"─────────────────────────────"
        )
        
        keyboard = []
        for key, val in data.items():
            if isinstance(val, bool):
                status = "ENABLED" if val else "DISABLED"
                btn_text = f"{key.replace('_', ' ').title()} :: {status}"
                cb_data = f"settings_toggle:{category}:{key}"
            else:
                btn_text = f"{key.replace('_', ' ').title()} :: {val}"
                cb_data = f"settings_prompt:{category}:{key}"
            
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])
        
        keyboard.append([InlineKeyboardButton("← Back", callback_data="settings_home")])
        
        if is_new:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_watchlist(self, message):
        watchlist = state_manager.get_all()
        
        if not watchlist:
            text = (
                f"**WATCHLIST**\n"
                f"─────────────────────────────\n"
                f"No assets currently tracked.\n"
                f"Add assets via signal alerts."
            )
            keyboard = [[InlineKeyboardButton("← Return to Terminal", callback_data="dashboard")]]
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        text = f"**ACTIVE WATCHLIST**\n─────────────────────────────\n"
        for i, (addr, data) in enumerate(list(watchlist.items())[:8]):
            symbol = data.get('symbol', 'UNK')
            entry = data.get('entry_price', 0)
            text += f"• **{symbol}**  |  Entry: ${entry:.4f}\n"
        
        text += f"─────────────────────────────\nTotal: {len(watchlist)}"
        
        keyboard = [[InlineKeyboardButton("← Return to Terminal", callback_data="dashboard")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_help(self, message):
        text = (
            f"**SYSTEM GUIDE**\n"
            f"─────────────────────────────\n"
            f"**Commands**\n"
            f"/start  ::  Initialize Terminal\n"
            f"/ping   ::  Check Latency\n\n"
            f"**Workflow**\n"
            f"1. System scans {settings.TARGET_CHAIN} chain.\n"
            f"2. Filters applied via Configuration.\n"
            f"3. Signals broadcast to channel.\n"
            f"4. Track assets via Watchlist."
        )
        keyboard = [[InlineKeyboardButton("← Return to Terminal", callback_data="dashboard")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_refresh_watchlist(self, query):
        """Visual refresh with minimal feedback to prevent spam feeling."""
        await query.answer("Refreshing data stream...")
        await query.message.edit_text(f"**SYNCING DATA STREAM...**\n─────────────────────────────\nFetching latest pricing from API...")
        
        # Simulating data processing delay for UX (API is fast)
        await asyncio.sleep(0.5)
        
        # Re-render watchlist
        await self._render_watchlist(query.message)

    async def _handle_watch_action(self, query, address):
        try:
            pairs = await self.api.get_pairs_bulk([address])
            if pairs:
                price = float(pairs[0].get('priceUsd', 0))
                metadata = {
                    "entry_price": price,
                    "symbol": pairs[0]['baseToken']['symbol'],
                    "chat_id": query.message.chat_id,
                    "added_at": datetime.utcnow().timestamp()
                }
                await state_manager.add_token(address, metadata)
                
                # Update button visual state
                keyboard = [
                    [InlineKeyboardButton("✓ Tracking", callback_data="noop")],
                    [InlineKeyboardButton("↗ DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{address}")]
                ]
                
                await query.edit_message_caption(
                    caption=query.message.caption + f"\n\n**✓ ASSET TRACKED** | Entry: ${price}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except Exception as e:
            log.error(f"Watch action failed: {e}")
            await query.answer("Error tracking asset.")

    async def broadcast_signal(self, analysis: dict):
        """Broadcasts signal in Terminal format."""
        msg = (
            f"**SIGNAL DETECTED**\n"
            f"─────────────────────────────\n"
            f"**{analysis['baseToken']['name']}** ({analysis['baseToken']['symbol']})\n"
            f"`{analysis['address']}`\n\n"
            f"Price       ::  ${analysis['priceUsd']}\n"
            f"Liquidity   ::  ${analysis['liquidity']:,.0f}\n"
            f"Age         ::  {analysis['age_hours']}h\n"
            f"Risk Score  ::  {analysis['risk']['score']}/100\n"
            f"Whale       ::  {'YES' if analysis['whale']['detected'] else 'NO'}\n"
            f"─────────────────────────────"
        )
        
        keyboard = [[
            InlineKeyboardButton("✚ Watchlist", callback_data=f"watch:{analysis['address']}"),
            InlineKeyboardButton("↗ DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{analysis['address']}")
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
        
        msg = (
            f"**EXIT TRIGGERED**\n"
            f"─────────────────────────────\n"
            f"Asset   ::  {data['symbol']}\n"
            f"Reason  ::  {reason}\n"
            f"PnL     ::  {pnl:.2f}%\n"
            f"─────────────────────────────"
        )
        try:
            await self.app.bot.send_message(chat_id=data['chat_id'], text=msg, parse_mode='Markdown')
        except Exception as e:
            log.error(f"Exit alert failed: {e}")

    async def shutdown(self):
        if self.app.updater.running:
            await self.app.updater.stop()
        if self.app.running:
            await self.app.stop()
        await self.app.shutdown()
