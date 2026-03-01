from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from config.settings import settings, strategy
from utils.logger import log
from utils.state import state_manager
from utils.helpers import get_current_time_str, get_time_obj, TIMEZONE
from api.dexscreener import DexScreenerAPI
from system.health import SystemHealth
import asyncio
import time
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
        
        # Text Input
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
        """
        Triggered via /ping command. Sends a new message.
        """
        # Calculate command processing latency
        request_time = update.message.date.replace(tzinfo=TIMEZONE)
        now = datetime.now(TIMEZONE)
        latency = (now - request_time).total_seconds() * 1000
        
        await self._render_diagnostics(update.message, latency_override=latency, is_new=True)

    # --- Interaction Router ---

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        
        data = query.data.split(":")
        action = data[0]
        
        if action != "settings_edit_val":
             context.user_data['edit_mode'] = None

        try:
            # Dashboard Actions
            if action == "dashboard":
                await query.answer()
                await self._render_dashboard(query.message)
            
            elif action == "dashboard_refresh":
                await self._handle_dashboard_refresh(query)

            elif action == "ping_action":
                await query.answer() # Ack the click
                # Trigger internal diagnostics edit
                await self._render_diagnostics(query.message, is_new=False)

            # Settings Navigation
            elif action == "settings_home":
                await query.answer()
                await self._render_settings_home(query.message)
            elif action == "settings_cat":
                await query.answer()
                category = data[1]
                await self._render_settings_category(query.message, category)
            elif action == "settings_toggle":
                await query.answer()
                category, key = data[1], data[2]
                current = getattr(strategy, category).get(key, False)
                await strategy.update_setting(category, key, not current)
                await self._render_settings_category(query.message, category)
            elif action == "settings_prompt":
                await query.answer()
                category, key = data[1], data[2]
                context.user_data['edit_mode'] = {'cat': category, 'key': key}
                await query.message.reply_text(
                    f"📝 **EDIT PARAMETER**\n`{key}`\n\nCurrent: `{getattr(strategy, category).get(key)}`\n"
                    f"Enter new value:",
                    parse_mode='Markdown'
                )

            # Watchlist Actions
            elif action == "watchlist_view":
                await query.answer()
                await self._render_watchlist(query.message)
            elif action == "watchlist_refresh":
                await self._handle_refresh_watchlist(query)
            elif action == "watch":
                await query.answer()
                address = data[1] if len(data) > 1 else None
                if address: await self._handle_watch_action(query, address)

            # Info
            elif action == "help_menu":
                await query.answer()
                await self._render_help(query.message)

        except Exception as e:
            log.error(f"UI Interaction Error ({action}): {e}")
            try:
                await query.answer("Request Error", show_alert=True)
            except:
                pass

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        edit_state = context.user_data.get('edit_mode')
        if not edit_state: return 

        try:
            val = update.message.text.strip()
            cat = edit_state['cat']
            key = edit_state['key']
            
            await strategy.update_setting(cat, key, val)
            
            await update.message.reply_text(f"✔ **Saved:** `{key}` → `{val}`", parse_mode='Markdown')
            context.user_data['edit_mode'] = None
            await self._render_settings_category(update.message, cat, is_new=True)
            
        except Exception:
            await update.message.reply_text("✖ Invalid format.")

    # --- UI Renderers ---

    async def _render_dashboard(self, message, is_new=False):
        """
        Renders the main trading dashboard.
        """
        watchlist_count = len(state_manager.get_all())
        sys_metrics = SystemHealth.get_metrics()
        
        safe_status = "ON" if sys_metrics['safe_mode'] else "OFF"
        status_emoji = "🟡" if sys_metrics['safe_mode'] else "🟢"
        
        heartbeat = f"{settings.POLL_INTERVAL}s"
        timestamp = get_current_time_str("%H:%M IST")

        text = (
            f"📡 **DEXSCREENER TERMINAL**\n"
            f"────────────────\n\n"
            f"{status_emoji} **Status:** `Online`\n"
            f"⚡ **Heartbeat:** `{heartbeat}`\n"
            f"📊 **Active Watches:** `{watchlist_count}`\n"
            f"🎯 **Active Filters:** `{len(strategy.filters)}`\n"
            f"🛡 **Safe Mode:** `{safe_status}`\n"
            f"🕒 **Last Refresh:** `{timestamp}`\n\n"
            f"────────────────\n"
            f"Select an action below:"
        )

        keyboard = [
            [
                InlineKeyboardButton("📈 Watchlist", callback_data="watchlist_view"),
                InlineKeyboardButton("🔄 Refresh", callback_data="dashboard_refresh")
            ],
            [
                InlineKeyboardButton("⚙ Settings", callback_data="settings_home"),
                InlineKeyboardButton("❓ Help", callback_data="help_menu")
            ],
            [
                InlineKeyboardButton("🏓 Ping", callback_data="ping_action")
            ]
        ]
        
        markup = InlineKeyboardMarkup(keyboard)
        if is_new:
            await message.reply_text(text, reply_markup=markup, parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=markup, parse_mode='Markdown')

    async def _render_diagnostics(self, message, latency_override=None, is_new=False):
        """
        Renders the System Diagnostics Panel (Ping Result).
        """
        # Calculate execution latency if not provided
        start_time = time.time()
        sys_metrics = SystemHealth.get_metrics()
        end_time = time.time()
        
        if latency_override:
            latency_ms = latency_override
        else:
            latency_ms = (end_time - start_time) * 1000

        watches = len(state_manager.get_all())
        status_icon = "🟢" if not sys_metrics['safe_mode'] else "🟡"
        status_text = "HEALTHY" if not sys_metrics['safe_mode'] else "DEGRADED"
        
        text = (
            f"🏓 **PONG**\n"
            f"────────────────\n"
            f"{status_icon} **System Status:** `{status_text}`\n"
            f"⚡ **Latency:** `{latency_ms:.0f} ms`\n"
            f"🖥 **CPU Usage:** `{sys_metrics['cpu']}%`\n"
            f"🧠 **RAM Usage:** `{sys_metrics['ram']}%`\n"
            f"👁 **Active Watches:** `{watches}`\n"
            f"🛡 **Safe Mode:** `{'ACTIVE' if sys_metrics['safe_mode'] else 'INACTIVE'}`\n"
            f"📊 **Market Regime:** `NORMAL`\n"
            f"🕒 **Time:** `{get_current_time_str()}`"
        )
        
        # Add a back button so user isn't stuck
        keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
        
        if is_new:
            await message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await message.edit_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _handle_dashboard_refresh(self, query):
        """
        In-place refresh of the dashboard metrics.
        """
        await query.answer("Syncing System Metrics...")
        
        try:
            start = time.time()
            # Lightweight connectivity check
            await self.api.get_pairs_by_chain(settings.TARGET_CHAIN)
            latency = (time.time() - start) * 1000
            
            watchlist_count = len(state_manager.get_all())
            sys_metrics = SystemHealth.get_metrics()
            safe_status = "ON" if sys_metrics['safe_mode'] else "OFF"
            status_emoji = "🟡" if sys_metrics['safe_mode'] else "🟢"
            timestamp = get_current_time_str("%H:%M IST")

            text = (
                f"📡 **DEXSCREENER TERMINAL**\n"
                f"────────────────\n\n"
                f"{status_emoji} **Status:** `Online`\n"
                f"⚡ **Latency:** `{latency:.0f} ms`\n"
                f"📊 **Active Watches:** `{watchlist_count}`\n"
                f"🎯 **Active Filters:** `{len(strategy.filters)}`\n"
                f"🛡 **Safe Mode:** `{safe_status}`\n"
                f"🕒 **Last Refresh:** `{timestamp}`\n\n"
                f"────────────────\n"
                f"Select an action below:"
            )
            
            keyboard = query.message.reply_markup
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
            
        except Exception as e:
            log.error(f"Dashboard Refresh Failed: {e}")
            await query.answer("Connection Error", show_alert=True)

    async def _render_settings_home(self, message):
        text = (
            "⚙ **SYSTEM CONFIGURATION**\n"
            "────────────────\n"
            "Select a module to configure:"
        )
        keyboard = [
            [InlineKeyboardButton("🔍 Filters", callback_data="settings_cat:filters")],
            [InlineKeyboardButton("⚖ Scoring", callback_data="settings_cat:weights")],
            [InlineKeyboardButton("🛡 Thresholds", callback_data="settings_cat:thresholds")],
            [InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_settings_category(self, message, category, is_new=False):
        data = getattr(strategy, category)
        text = f"⚙ **EDITING: {category.upper()}**\nClick to modify:"
        
        keyboard = []
        for key, val in data.items():
            if isinstance(val, bool):
                status = "ON" if val else "OFF"
                btn_text = f"{key} [{status}]"
                cb_data = f"settings_toggle:{category}:{key}"
            else:
                btn_text = f"{key}: {val}"
                cb_data = f"settings_prompt:{category}:{key}"
            
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="settings_home")])
        
        markup = InlineKeyboardMarkup(keyboard)
        if is_new:
            await message.reply_text(text, reply_markup=markup, parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=markup, parse_mode='Markdown')

    async def _render_watchlist(self, message):
        watchlist = state_manager.get_all()
        
        if not watchlist:
            text = (
                "📈 **WATCHLIST**\n"
                "────────────────\n"
                "No active tokens.\n"
                "Add tokens from signal alerts."
            )
            keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        text = "📈 **ACTIVE ASSETS**\n────────────────\n"
        items = list(watchlist.items())[:8]
        for _, data in items:
            symbol = data.get('symbol', 'UNK')
            price = data.get('entry_price', 0)
            text += f"• **{symbol:<6}** | ${price:.4f}\n"
        
        if len(watchlist) > 8:
            text += f"\n+ {len(watchlist)-8} more..."

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Prices", callback_data="watchlist_refresh")],
            [InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_refresh_watchlist(self, query):
        await query.answer("Fetching prices...")
        await query.message.edit_text("⏳ **Syncing Market Data...**")
        
        watchlist = state_manager.get_all()
        if not watchlist:
             await self._render_watchlist(query.message)
             return

        try:
            addresses = list(watchlist.keys())
            await self.api.get_pairs_bulk(addresses)
            await self._render_watchlist(query.message)

        except Exception as e:
            log.error(f"Refresh failed: {e}")
            await query.message.edit_text("❌ **Sync Failed**", parse_mode='Markdown')
            await asyncio.sleep(1)
            await self._render_dashboard(query.message)

    async def _handle_watch_action(self, query, address):
        try:
            pairs = await self.api.get_pairs_bulk([address])
            if pairs:
                price = float(pairs[0].get('priceUsd', 0))
                symbol = pairs[0]['baseToken']['symbol']
                
                metadata 
