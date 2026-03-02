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
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user: return

        admin_ids = settings.get_admins()
        
        if user.id not in admin_ids:
            if update.callback_query:
                await update.callback_query.answer("🚫 Access Denied", show_alert=True)
            return

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
        self.app.add_handler(CommandHandler("settings_guide", self.cmd_settings_guide))
        
        # Callbacks - Single Entry Point
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Text Input
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, self.handle_text_input))

    async def initialize(self):
        log.info("Initializing Signal Bot UI...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        log.info("Signal Bot Polling Started")

    @admin_restricted
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await self._render_dashboard(update.message, is_new=True)

    @admin_restricted
    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🏓 Pong!")

    @admin_restricted
    async def cmd_settings_guide(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = "📘 **STRATEGY GUIDE**\nUse /start > Settings to edit parameters."
        await update.message.reply_text(text, parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._restricted_callback_logic(update, context)

    @admin_restricted
    async def _restricted_callback_logic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data.split(":")
        action = data[0]
        
        # Clear edit mode unless specifically editing
        if action != "settings_prompt":
             context.user_data['edit_mode'] = None

        log.debug(f"Callback Action: {action} | Data: {query.data}")

        try:
            if action == "signal_refresh":
                await query.answer("Refreshing Signal...")
                if len(data) > 1: await self._handle_signal_refresh(query, data[1])

            elif action == "dashboard":
                await query.answer()
                await self._render_dashboard(query.message)
            
            elif action == "dashboard_refresh":
                await query.answer("Refreshing Dashboard...")
                await self._handle_dashboard_refresh(query)

            elif action == "api_manual_fetch":
                await query.answer("Initiating API Fetch...")
                await self._handle_manual_api_fetch(query)

            elif action == "settings_home":
                await query.answer()
                await self._render_settings_home(query.message)
            
            elif action == "settings_cat":
                await query.answer()
                if len(data) > 1: await self._render_settings_category(query.message, data[1])
            
            elif action == "settings_toggle":
                await query.answer("Toggling...")
                if len(data) >= 3: await self._handle_setting_toggle(query, data[1], data[2])
            
            elif action == "settings_prompt":
                await query.answer()
                if len(data) >= 3: await self._handle_setting_prompt(query, data[1], data[2], context)

            elif action == "watchlist_view":
                await query.answer()
                await self._render_watchlist(query.message)
            elif action == "watchlist_refresh":
                await query.answer("Updating Watchlist...")
                await self._handle_refresh_watchlist(query)
            elif action == "watch":
                await query.answer("Adding to Watchlist...")
                if len(data) > 1: await self._handle_watch_action(query, data[1])

            elif action == "help_menu":
                await query.answer()
                await self._render_help(query.message)
            
            elif action == "ping_action":
                await query.answer("Running Diagnostics...")
                await self._render_diagnostics_panel(query.message)
            
            elif action == "noop":
                await query.answer()

            else:
                log.warning(f"Unhandled callback action: {action}")
                await query.answer("Unknown Action")

        except Exception as e:
            log.error(f"UI Interaction Error ({action}): {e}")
            try: await query.answer("Error processing request")
            except: pass

    @admin_restricted
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        edit_state = context.user_data.get('edit_mode')
        if not edit_state: return 

        try:
            val = float(update.message.text.strip())
            cat = edit_state['cat']
            key = edit_state['key']
            
            await strategy.update_setting(cat, key, val)
            
            await update.message.reply_text(f"✔ **Saved:** `{key}` → `{val}`", parse_mode='Markdown')
            context.user_data['edit_mode'] = None
            
            await self._render_settings_category(update.message, cat, is_new=True)
            
        except ValueError:
            await update.message.reply_text("✖ Numeric value required.")
        except Exception as e:
            log.error(f"Settings input error: {e}")
            await update.message.reply_text("✖ Update failed.")

    # --- Handlers ---

    async def _handle_setting_toggle(self, query, category, key):
        current = getattr(strategy, category).get(key, False)
        await strategy.update_setting(category, key, not current)
        await self._render_settings_category(query.message, category)

    async def _handle_setting_prompt(self, query, category, key, context):
        context.user_data['edit_mode'] = {'cat': category, 'key': key}
        desc = strategy.get_parameter_description(category, key)
        await query.message.reply_text(
            f"📝 **EDIT: {key}**\n\nℹ {desc}\n\nCurrent: `{getattr(strategy, category).get(key)}`\nEnter new numeric value:",
            parse_mode='Markdown'
        )

    # --- UI Renderers ---

    async def _render_dashboard(self, message, is_new=False):
        sys = SystemHealth.get_metrics()
        wl_count = len(state_manager.get_all())
        status = "🟢" if not sys['safe_mode'] else "🟡"
        timestamp = get_ist_time_str("%H:%M IST")
        limit = strategy.system.get('fetch_limit', 300)
        
        text = (
            f"📡 **DEXSCREENER TERMINAL**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{status} **Status:** `Online`\n"
            f"⚡ **Heartbeat:** `{settings.POLL_INTERVAL}s`\n"
            f"📊 **Watches:** `{wl_count}`\n"
            f"🎯 **Fetch Limit:** `{limit}`\n"
            f"🕒 **Last:** `{timestamp}`\n━━━━━━━━━━━━━━━━━━━━\n"
            f"Select action:"
        )
        keyboard = [
            [InlineKeyboardButton("📈 Watchlist", callback_data="watchlist_view"), InlineKeyboardButton("🔄 Refresh", callback_data="dashboard_refresh")],
            [InlineKeyboardButton("⚙ Settings", callback_data="settings_home"), InlineKeyboardButton("❓ Help", callback_data="help_menu")],
            [InlineKeyboardButton("🌐 API Request", callback_data="api_manual_fetch")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        if is_new: await message.reply_text(text, reply_markup=markup, parse_mode='Markdown')
        else: await message.edit_text(text, reply_markup=markup, parse_mode='Markdown')

    async def _render_diagnostics_panel(self, message):
        start = time.perf_counter()
        sys = SystemHealth.get_metrics()
        end = time.perf_counter()
        latency = (end - start) * 1000
        text = (
            f"**DIAGNOSTICS**\n━━━━━━━━━━━━━━━━\n"
            f"🖥 CPU: `{sys['cpu']}%`\n"
            f"🧠 RAM: `{sys['ram']}%`\n"
            f"⚡ Latency: `{latency:.0f}ms`\n"
            f"🕒 Uptime: `{sys['uptime_seconds']}s`"
        )
        kb = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
        await message.edit_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    async def _handle_dashboard_refresh(self, query):
        await self._render_dashboard(query.message, is_new=False)

    async def _render_settings_home(self, message):
        text = "⚙ **CONFIG**\nSelect module:"
        kb = [
            [InlineKeyboardButton("🔍 Filters", callback_data="settings_cat:filters")],
            [InlineKeyboardButton("⚖ Weights", callback_data="settings_cat:weights")],
            [InlineKeyboardButton("🛡 Risk", callback_data="settings_cat:thresholds")],
            [InlineKeyboardButton("🔧 System", callback_data="settings_cat:system")],
            [InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    async def _render_settings_category(self, message, category, is_new=False):
        data = getattr(strategy, category)
        text = f"⚙ **EDIT: {category.upper()}**"
        kb = []
        for key, val in data.items():
            if isinstance(val, bool):
                lbl = f"{key} [{'ON' if val else 'OFF'}]"
                cb = f"settings_toggle:{category}:{key}"
            else:
                lbl = f"{key}: {val}"
                cb = f"settings_prompt:{category}:{key}"
            kb.append([InlineKeyboardButton(lbl, callback_data=cb)])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="settings_home")])
        
        markup = InlineKeyboardMarkup(kb)
        if is_new: await message.reply_text(text, reply_markup=markup, parse_mode='Markdown')
        else: await message.edit_text(text, reply_markup=markup, parse_mode='Markdown')

    async def _render_watchlist(self, message):
        wl = state_manager.get_all()
        if not wl:
            text = "📈 **WATCHLIST**\nEmpty."
            kb = [[InlineKeyboardButton("🔙", callback_data="dashboard")]]
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            return
        
        text = "📈 **WATCHLIST**\n"
        for _, d in list(wl.items())[:8]:
            text += f"• **{d.get('symbol')}** ${d.get('entry_price'):.4f}\n"
        
        kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="watchlist_refresh"), InlineKeyboardButton("🔙", callback_data="dashboard")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    async def _handle_refresh_watchlist(self, query):
        keys = list(state_manager.get_all().keys())
        if keys: await self.api.get_pairs_bulk(keys)
        await self._render_watchlist(query.message)

    async def _handle_watch_action(self, query, address):
        pairs = await self.api.get_pairs_bulk([address])
        if pairs:
            p = pairs[0]
            await state_manager.add_token(address, {"entry_price": float(p.get('priceUsd',0)), "symbol": p['baseToken']['symbol'], "chat_id": query.message.chat_id})
            kb = [
                [InlineKeyboardButton("✔ Monitoring", callback_data="noop")],
                [InlineKeyboardButton("↗ Chart", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{address}")]
            ]
            await query.edit_message_caption(caption=query.message.caption + "\n\n✅ **Added**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    async def _handle_manual_api_fetch(self, query):
        await query.message.edit_text("⏳ **Fetching...**")
        start = time.time()
        pairs = await self.api.get_pairs_by_chain(settings.TARGET_CHAIN)
        dur = time.time() - start
        msg = f"✅ **Fetch Complete**\nItems: `{len(pairs)}`\nTime: `{dur:.2f}s`"
        kb = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
        await query.message.edit_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    async def _handle_signal_refresh(self, query, address):
        pairs = await self.api.get_pairs_bulk([address])
        if not pairs:
            await query.message.edit_text("❌ Token Not Found", parse_mode='Markdown')
            return
        
        p = pairs[0]
        analysis = AnalysisEngine.analyze_token(p)
        if not analysis:
            await query.message.edit_text("❌ Filtered Out", parse_mode='Markdown')
            return
            
        metrics = analysis.get('metrics', {})
        msg = (
            f"💎 **GEM DETECTED** | {analysis['baseToken']['symbol']}\n"
            f"────────────────\n"
            f"💰 **Price:** `${analysis.get('priceUsd', '0')}`\n"
            f"💧 **Liquidity:** `${analysis.get('liquidity', 0):,.0f}`\n"
            f"📊 **FDV:** `${analysis.get('fdv', 0):,.0f}`\n"
            f"⏳ **Age:** `{analysis.get('age_hours', 0)}h`\n"
            f"🌊 **Vol 1H:** `${metrics.get('volume_h1', 0):,.0f}`\n"
            f"📈 **Change 1H:** `{metrics.get('price_change_h1', 0)}%`\n"
            f"🎯 **Score:** `{analysis['risk']['score']}/100`\n"
            f"────────────────\n"
            f"🔄 **Refreshed:** `{get_ist_time_str()}`\n"
            f"`{analysis['address']}`"
        )
        kb = [
            [InlineKeyboardButton("👁 Watch", callback_data=f"watch:{analysis['address']}"),
             InlineKeyboardButton("🔄 Refresh", callback_data=f"signal_refresh:{analysis['address']}")],
            [InlineKeyboardButton("↗ DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{analysis['address']}")]
        ]
        await query.message.edit_text(text=msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    async def broadcast_signal(self, analysis: dict):
        metrics = analysis.get('metrics', {})
        msg = (
            f"💎 **GEM DETECTED** | {analysis['baseToken']['symbol']}\n"
            f"────────────────\n"
            f"💰 **Price:** `${analysis.get('priceUsd', '0')}`\n"
            f"💧 **Liquidity:** `${analysis.get('liquidity', 0):,.0f}`\n"
            f"📊 **FDV:** `${analysis.get('fdv', 0):,.0f}`\n"
            f"⏳ **Age:** `{analysis.get('age_hours', 0)}h`\n"
            f"🌊 **Vol 1H:** `${metrics.get('volume_h1', 0):,.0f}`\n"
            f"📈 **Change 1H:** `{metrics.get('price_change_h1', 0)}%`\n"
            f"🎯 **Score:** `{analysis['risk']['score']}/100`\n"
            f"────────────────\n"
            f"🕒 **Detected:** `{get_ist_time_str()}`\n"
            f"`{analysis['address']}`"
        )
        kb = [
            [InlineKeyboardButton("👁 Watch", callback_data=f"watch:{analysis['address']}"),
             InlineKeyboardButton("🔄 Refresh", callback_data=f"signal_refresh:{analysis['address']}")],
            [InlineKeyboardButton("↗ DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{analysis['address']}")]
        ]
        try:
            await self.app.bot.send_message(chat_id=settings.CHANNEL_ID, text=msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            log.error(f"Broadcast failed: {e}")

    async def send_exit_alert(self, address: str, pnl: float, reason: str):
        data = state_manager.get_all().get(address)
        if not data: return
        msg = f"🔔 **EXIT** {data['symbol']}\nReason: {reason}\nPnL: {pnl:.2f}%"
        try:
            await self.app.bot.send_message(chat_id=data['chat_id'], text=msg, parse_mode='Markdown')
        except Exception: pass

    async def _render_help(self, message):
        await message.edit_text("ℹ **HELP**\nUse /start to reset.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="dashboard")]]), parse_mode='Markdown')

    async def shutdown(self):
        if self.app.updater.running: await self.app.updater.stop()
        if self.app.running: await self.app.stop()
        await self.app.shutdown()
