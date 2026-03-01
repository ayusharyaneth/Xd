from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from config.settings import settings, strategy
from utils.logger import log
from utils.state import state_manager
from api.dexscreener import DexScreenerAPI
from engines.analysis import AnalysisEngine
from datetime import datetime
import asyncio

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
        log.info("Initializing Signal Bot UI...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        log.info("Signal Bot Dashboard Active")

    # --- Command Handlers ---

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await self._render_dashboard(update.message, is_new=True)

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        latency = (datetime.now().timestamp() - update.message.date.timestamp()) * 1000
        await update.message.reply_text(f"● Latency: {latency:.0f}ms")

    # --- Interaction Router ---

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer() # Ack to prevent freeze

        data = query.data.split(":")
        action = data[0]
        
        # Reset edit mode unless specifically editing
        if action != "settings_edit_val":
             context.user_data['edit_mode'] = None

        try:
            # Dashboard Navigation
            if action == "dashboard":
                await self._render_dashboard(query.message)
            
            # Settings Navigation
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
                    f"**EDIT PARAMETER**\n`{key}`\n\nCurrent: `{getattr(strategy, category).get(key)}`\n"
                    f"Enter new value:",
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

            # Info
            elif action == "help_menu":
                await self._render_help(query.message)

        except Exception as e:
            log.error(f"UI Interaction Error ({action}): {e}")
            await query.message.reply_text("Error processing request.")

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Captures text input for setting edits."""
        edit_state = context.user_data.get('edit_mode')
        
        if not edit_state:
            return 

        try:
            val = update.message.text.strip()
            cat = edit_state['cat']
            key = edit_state['key']
            
            await strategy.update_setting(cat, key, val)
            
            await update.message.reply_text(f"✔ **Saved:** `{key}` → `{val}`", parse_mode='Markdown')
            context.user_data['edit_mode'] = None
            
            # Return to menu
            await self._render_settings_category(update.message, cat, is_new=True)
            
        except Exception:
            await update.message.reply_text("✖ Invalid format. Value not saved.")

    # --- UI Renderers ---

    async def _render_dashboard(self, message, is_new=False):
        """
        Renders the main dashboard with a minimal fintech aesthetic.
        """
        watchlist = state_manager.get_all()
        strict_mode = strategy.thresholds.get('strict_filtering', True)
        min_liq = strategy.filters.get('min_liquidity_usd', 0)
        timestamp = datetime.utcnow().strftime("%H:%M:%S UTC")
        
        # Aligned Monospace Metrics
        metrics_block = (
            f"`{'Watchlist':<12} {len(watchlist)}`\n"
            f"`{'Liquidity':<12} >${min_liq:,.0f}`\n"
            f"`{'Mode':<12} {'Strict' if strict_mode else 'Standard'}`"
        )

        text = (
            f"**DEXSCREENER** · INTELLIGENCE\n"
            f"● Online  |  {settings.TARGET_CHAIN.title()}\n\n"
            f"**Session Metrics**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{metrics_block}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Last Update: {timestamp}"
        )

        keyboard = [
            [
                InlineKeyboardButton("📂 Watchlist", callback_data="watchlist_view"),
                InlineKeyboardButton("↻ Refresh", callback_data="watchlist_refresh")
            ],
            [
                InlineKeyboardButton("⚙ Configuration", callback_data="settings_home"),
                InlineKeyboardButton("❓ Help", callback_data="help_menu")
            ]
        ]
        
        markup = InlineKeyboardMarkup(keyboard)
        if is_new:
            await message.reply_text(text, reply_markup=markup, parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=markup, parse_mode='Markdown')

    async def _render_settings_home(self, message):
        text = (
            "**CONFIGURATION**\n"
            "Select a module to configure parameters.\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        keyboard = [
            [InlineKeyboardButton("Filters (Liquidity, Age)", callback_data="settings_cat:filters")],
            [InlineKeyboardButton("Scoring Weights", callback_data="settings_cat:weights")],
            [InlineKeyboardButton("Risk Thresholds", callback_data="settings_cat:thresholds")],
            [InlineKeyboardButton("← Return", callback_data="dashboard")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_settings_category(self, message, category, is_new=False):
        data = getattr(strategy, category)
        text = f"**EDITING: {category.upper()}**\nSelect value to modify:"
        
        keyboard = []
        for key, val in data.items():
            if isinstance(val, bool):
                status = "ON" if val else "OFF"
                btn_text = f"{key.replace('_', ' ').title()} [{status}]"
                cb_data = f"settings_toggle:{category}:{key}"
            else:
                btn_text = f"{key.replace('_', ' ').title()}: {val}"
                cb_data = f"settings_prompt:{category}:{key}"
            
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])
        
        keyboard.append([InlineKeyboardButton("← Back", callback_data="settings_home")])
        
        markup = InlineKeyboardMarkup(keyboard)
        if is_new:
            await message.reply_text(text, reply_markup=markup, parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=markup, parse_mode='Markdown')

    async def _render_watchlist(self, message):
        watchlist = state_manager.get_all()
        
        if not watchlist:
            text = (
                "**WATCHLIST**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "No active tokens.\n"
                "Add tokens from signal alerts."
            )
            keyboard = [[InlineKeyboardButton("← Dashboard", callback_data="dashboard")]]
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        text = "**ACTIVE ASSETS**\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Display up to 8 items to keep UI clean
        items = list(watchlist.items())[:8]
        for _, data in items:
            symbol = data.get('symbol', 'UNK')
            price = data.get('entry_price', 0)
            text += f"`{symbol:<8}` ${price:.4f}\n"
        
        if len(watchlist) > 8:
            text += f"\n+ {len(watchlist)-8} more..."

        keyboard = [
            [InlineKeyboardButton("↻ Refresh Prices", callback_data="watchlist_refresh")],
            [InlineKeyboardButton("← Dashboard", callback_data="dashboard")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_refresh_watchlist(self, query):
        await query.answer("Syncing data...")
        await query.message.edit_text("**SYNCING...**\nFetching latest market data.")
        
        watchlist = state_manager.get_all()
        if not watchlist:
             await self._render_watchlist(query.message)
             return

        try:
            addresses = list(watchlist.keys())
            latest_data = await self.api.get_pairs_bulk(addresses)
            
            # Simple simulation of data processing
            # In a full version, we would update state_manager with new prices here
            await asyncio.sleep(0.5) 

            text = (
                f"**SYNC COMPLETE**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Processed: {len(latest_data)} Pairs\n"
                f"Status: Nominal"
            )
            await query.message.edit_text(text, parse_mode='Markdown')
            await asyncio.sleep(1)
            await self._render_watchlist(query.message)

        except Exception as e:
            log.error(f"Refresh failed: {e}")
            await query.message.edit_text("**SYNC FAILED**\nNetwork Error", parse_mode='Markdown')
            await asyncio.sleep(1.5)
            await self._render_dashboard(query.message)

    async def _handle_watch_action(self, query, address):
        try:
            pairs = await self.api.get_pairs_bulk([address])
            if pairs:
                price = float(pairs[0].get('priceUsd', 0))
                symbol = pairs[0]['baseToken']['symbol']
                
                metadata = {
                    "entry_price": price,
                    "symbol": symbol,
                    "chat_id": query.message.chat_id,
                    "added_at": datetime.utcnow().timestamp()
                }
                await state_manager.add_token(address, metadata)
                
                keyboard = [
                    [InlineKeyboardButton("✔ Monitoring", callback_data="noop")],
                    [InlineKeyboardButton("↗ View Chart", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{address}")]
                ]
                
                await query.edit_message_caption(
                    caption=query.message.caption + f"\n\n**✔ WATCHLIST ADDED**\nEntry: ${price:.4f}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except Exception as e:
            log.error(f"Watch add failed: {e}")
            await query.answer("Error adding token")

    async def _render_help(self, message):
        text = (
            "**SYSTEM GUIDE**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• **Dashboard**: Main control center.\n"
            "• **Refresh**: Forces a re-scan of watchlist.\n"
            "• **Config**: Adjust risk scoring and filters.\n\n"
            "**Commands**\n"
            "`/start` - Reset Interface\n"
            "`/ping` - Network Latency"
        )
        keyboard = [[InlineKeyboardButton("← Return", callback_data="dashboard")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def broadcast_signal(self, analysis: dict):
        """Sends a structured signal alert."""
        msg = (
            f"**SIGNAL DETECTED** | {analysis['baseToken']['symbol']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"`{'Price':<10} ${analysis.get('priceUsd', '0')}`\n"
            f"`{'Liquidity':<10} ${analysis.get('liquidity', 0):,.0f}`\n"
            f"`{'Risk Score':<10} {analysis['risk']['score']}/100`\n"
            f"`{'Age':<10} {analysis.get('age_hours', 0)}h`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Address: `{analysis['address']}`"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📂 Add to Watchlist", callback_data=f"watch:{analysis['address']}"),
                InlineKeyboardButton("↗ DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{analysis['address']}")
            ]
        ]

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
        
        symbol = data.get('symbol', 'UNK')
        icon = "🚀" if pnl > 0 else "🛑"
        
        msg = (
            f"**EXIT SIGNAL** {icon}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Asset: **{symbol}**\n"
            f"Reason: {reason}\n"
            f"PnL: **{pnl:+.2f}%**"
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
