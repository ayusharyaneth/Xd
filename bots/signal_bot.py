from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from config.settings import settings, strategy
from utils.logger import log
from utils.state import state_manager
from utils.helpers import get_ist_time_str
from api.dexscreener import DexScreenerAPI
from system.health import SystemHealth
from engines.analysis import AnalysisEngine
from functools import wraps
import asyncio
import time

def admin_restricted(func):
    """
    Decorator to restrict handler access to admin users only.
    Unauthorized attempts are logged to a dedicated Telegram channel if configured.
    """
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        # Use the new property accessor for admin IDs
        admin_ids = settings.admin_list
        
        if user.id not in admin_ids:
            # 1. Reject User
            rejection_text = "🚫 This is a Private Project built for Personal use."
            
            if update.callback_query:
                await update.callback_query.answer("🚫 Access Denied", show_alert=True)
            elif update.message:
                await update.message.reply_text(rejection_text, parse_mode='Markdown')

            # 2. Log to Dedicated Channel (Only if configured)
            if settings.LOG_CHANNEL_ID:
                try:
                    action_type = "Command" if update.message else "Callback"
                    content = update.message.text if update.message else update.callback_query.data
                    username = f"@{user.username}" if user.username else "N/A"
                    timestamp = get_ist_time_str()
                    
                    log_msg = (
                        f"🚨 **Unauthorized Access Attempt**\n\n"
                        f"👤 **User ID:** `{user.id}`\n"
                        f"🧾 **Username:** {username}\n"
                        f"📩 **Action:** `{action_type}: {content}`\n"
                        f"🕒 **Time:** `{timestamp}`\n"
                        f"📡 **Chat ID:** `{update.effective_chat.id}`"
                    )
                    
                    await context.bot.send_message(
                        chat_id=settings.LOG_CHANNEL_ID,
                        text=log_msg,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    log.error(f"Failed to send security log: {e}")
            
            # Stop execution
            return

        # Proceed if authorized
        return await func(self, update, context, *args, **kwargs)
    return wrapper

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

    @admin_restricted
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await self._render_dashboard(update.message, is_new=True)

    @admin_restricted
    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg_date = update.message.date
        now_ts = time.time()
        msg_ts = msg_date.timestamp()
        latency_ms = max(0, (now_ts - msg_ts) * 1000)
        
        text, reply_markup = self._generate_diagnostics_content(latency_ms)
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    # --- Interaction Router ---

    @admin_restricted
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
                await query.answer("Running Diagnostics...")
                await self._render_diagnostics_panel(query.message)

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

    @admin_restricted
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

    # --- UI Generators ---

    def _generate_diagnostics_content(self, latency_ms: float):
        sys_metrics = SystemHealth.get_metrics()
        watches = len(state_manager.get_all())
        
        status_icon = "🟢" if not sys_metrics['safe_mode'] else "🟡"
        status_text = "HEALTHY" if not sys_metrics['safe_mode'] else "DEGRADED"
        
        text = (
            f"**SYSTEM DIAGNOSTICS**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{status_icon} **System Status:** `{status_text}`\n"
            f"⚡ **Latency:** `{latency_ms:.0f} ms`\n"
            f"🖥 **CPU Usage:** `{sys_metrics['cpu']}%`\n"
            f"🧠 **RAM Usage:** `{sys_metrics['ram']}%`\n"
            f"👁 **Active Watches:** `{watches}`\n"
            f"🛡 **Safe Mode:** `{'ACTIVE' if sys_metrics['safe_mode'] else 'INACTIVE'}`\n"
            f"📊 **Market Regime:** `NORMAL`\n"
            f"🕒 **Time:** `{get_ist_time_str()}`"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
        return text, InlineKeyboardMarkup(keyboard)

    # --- UI Renderers ---

    async def _render_diagnostics_panel(self, message):
        start = time.perf_counter()
        sys_metrics = SystemHealth.get_metrics() 
        end = time.perf_counter()
        latency_ms = (end - start) * 1000
        
        text, reply_markup = self._generate_diagnostics_content(latency_ms)
        await message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def _render_dashboard(self, message, is_new=False):
        watchlist_count = len(state_manager.get_all())
        sys_metrics = SystemHealth.get_metrics()
        
        safe_status = "ON" if sys_metrics['safe_mode'] else "OFF"
        status_emoji = "🟡" if sys_metrics['safe_mode'] else "🟢"
        heartbeat = f"{settings.POLL_INTERVAL}s"
        timestamp = get_ist_time_str("%H:%M IST")

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

    async def _handle_dashboard_refresh(self, query):
        await query.answer("Syncing System Metrics...")
        
        try:
            start = time.perf_counter()
            await self.api.get_pairs_by_chain(settings.TARGET_CHAIN)
            end = time.perf_counter()
            latency = (end - start) * 1000
            
            watchlist_count = len(state_manager.get_all())
            sys_metrics = SystemHealth.get_metrics()
            safe_status = "ON" if sys_metrics['safe_mode'] else "OFF"
            status_emoji = "🟡" if sys_metrics['safe_mode'] else "🟢"
            timestamp = get_ist_time_str("%H:%M IST")

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
            [InlineKeyboardButton("🔍 Filters (Liquidity, Age)", callback_data="settings_cat:filters")],
            [InlineKeyboardButton("⚖ Scoring Weights", callback_data="settings_cat:weights")],
            [InlineKeyboardButton("🛡 Risk Thresholds", callback_data="settings_cat:thresholds")],
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
                
                metadata = {
                    "entry_price": price,
                    "symbol": symbol,
                    "chat_id": query.message.chat_id,
                    "added_at": time.time()
                }
                await state_manager.add_token(address, metadata)
                
                keyboard = [
                    [InlineKeyboardButton("✔ Monitoring", callback_data="noop")],
                    [InlineKeyboardButton("↗ Chart", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{address}")]
                ]
                
                await query.edit_message_caption(
                    caption=query.message.caption + f"\n\n✅ **ADDED TO WATCHLIST**",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except Exception as e:
            log.error(f"Watch add failed: {e}")
            await query.answer("Error adding token")

    async def _render_help(self, message):
        text = (
            "❓ **SYSTEM GUIDE**\n"
            "────────────────\n"
            "**Control Panel**\n"
            "• **Watchlist**: Track saved tokens.\n"
            "• **Refresh**: Force system metric sync.\n"
            "• **Settings**: Configure algorithm.\n"
            "• **Ping**: detailed system health.\n\n"
            "**Automated Signals**\n"
            "Bot scans for new tokens meeting 'Filters'.\n"
            "Signals are sent to the channel."
        )
        keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def broadcast_signal(self, analysis: dict):
        msg = (
            f"💎 **GEM DETECTED** | {analysis['baseToken']['symbol']}\n"
            f"────────────────\n"
            f"💰 Price: ${analysis.get('priceUsd', '0')}\n"
            f"💧 Liquidity: ${analysis.get('liquidity', 0):,.0f}\n"
            f"📊 Score: {analysis['risk']['score']}/100\n"
            f"🐋 Whale: {'YES' if analysis['whale']['detected'] else 'NO'}\n"
            f"────────────────\n"
            f"`{analysis['address']}`"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("👁 Watch", callback_data=f"watch:{analysis['address']}"),
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
            f"🔔 **EXIT SIGNAL** {icon}\n"
            f"────────────────\n"
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
