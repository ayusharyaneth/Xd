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
            elif update.message:
                await update.message.reply_text("🚫 This is a Private Project built for Personal use.")
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
        await update.message.reply_text(f"🏓 Pong! Latency: {latency_ms:.0f}ms")

    @admin_restricted
    async def cmd_settings_guide(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays a guide for all strategy parameters."""
        text = (
            "📘 **STRATEGY CONFIGURATION GUIDE**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "**FILTER LOGIC:**\n"
            "All filters use **AND** logic. A token must pass ALL enabled checks to be signaled.\n\n"
            
            "**PARAMETERS:**\n\n"
            "🔹 **min_liquidity_usd**\n"
            "• DexScreener Field: `liquidity.usd`\n"
            "• Min pool liquidity required. Prevents rugs with $10 liq.\n\n"
            
            "🔹 **min_volume_h1**\n"
            "• DexScreener Field: `volume.h1`\n"
            "• Min trading volume in last hour. Ensures activity.\n\n"
            
            "🔹 **max_age_hours**\n"
            "• Calc: `(Current Time - pairCreatedAt)`\n"
            "• Max age of token. Filters out old/dead coins.\n\n"
            
            "🔹 **max_fdv / min_fdv**\n"
            "• DexScreener Field: `fdv`\n"
            "• Market Cap limits. Set 0 to disable.\n\n"
            
            "🔹 **strict_filtering**\n"
            "• If `True`: Tokens missing data (like age) are DROPPEd.\n"
            "• If `False`: Tokens missing data are PASSED (Riskier).\n\n"
            
            "💡 *Use /start > Settings to edit these values.*"
        )
        await update.message.reply_text(text, parse_mode='Markdown')

    # --- Interaction Router ---

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._restricted_callback_logic(update, context)

    @admin_restricted
    async def _restricted_callback_logic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data.split(":")
        action = data[0]
        
        if action != "settings_edit_val":
             context.user_data['edit_mode'] = None

        try:
            if action == "signal_refresh":
                address = data[1] if len(data) > 1 else None
                if address: await self._handle_signal_refresh(query, address)

            elif action == "dashboard":
                await query.answer()
                await self._render_dashboard(query.message)
            
            elif action == "dashboard_refresh":
                await self._handle_dashboard_refresh(query)

            elif action == "api_manual_fetch":
                await self._handle_manual_api_fetch(query)

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
                desc = strategy.get_parameter_description(category, key)
                await query.message.reply_text(
                    f"📝 **EDIT: {key}**\n\n"
                    f"ℹ {desc}\n\n"
                    f"Current: `{getattr(strategy, category).get(key)}`\n"
                    f"Enter new value:",
                    parse_mode='Markdown'
                )

            elif action == "watchlist_view":
                await query.answer()
                await self._render_watchlist(query.message)
            elif action == "watchlist_refresh":
                await self._handle_refresh_watchlist(query)
            elif action == "watch":
                await query.answer()
                address = data[1] if len(data) > 1 else None
                if address: await self._handle_watch_action(query, address)

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
            
            # This triggers save to strategy.yaml + reload
            await strategy.update_setting(cat, key, val)
            
            await update.message.reply_text(f"✔ **Saved:** `{key}` → `{val}`", parse_mode='Markdown')
            context.user_data['edit_mode'] = None
            await self._render_settings_category(update.message, cat, is_new=True)
            
        except Exception:
            await update.message.reply_text("✖ Invalid format. Please enter a valid number.")

    # --- UI Renderers ---

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
                InlineKeyboardButton("🌐 API Request", callback_data="api_manual_fetch")
            ]
        ]
        
        markup = InlineKeyboardMarkup(keyboard)
        if is_new:
            await message.reply_text(text, reply_markup=markup, parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=markup, parse_mode='Markdown')

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
                # Add units/context if possible, keeping it brief
                btn_text = f"{key}: {val}"
                cb_data = f"settings_prompt:{category}:{key}"
            
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="settings_home")])
        
        markup = InlineKeyboardMarkup(keyboard)
        if is_new:
            await message.reply_text(text, reply_markup=markup, parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=markup, parse_mode='Markdown')
            
    # --- Other handlers (watchlist, api fetch, etc.) remain as previously implemented ---
    # Included full file above implies they are part of the class but truncated here for brevity
    # ensuring they are present in the actual output if modified.
    
    async def _handle_manual_api_fetch(self, query):
        await query.answer("Initiating API Request...")
        await query.message.edit_text("⏳ **Fetching Data from DexScreener...**\nChain: `solana`")
        
        start_time = time.time()
        try:
            pairs = await self.api.get_pairs_by_chain(settings.TARGET_CHAIN)
            count = len(pairs) if pairs else 0
            
            timestamp = get_ist_time_str()
            duration = time.time() - start_time
            
            msg = (
                f"✅ **API Fetch Successful**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 **Chain:** `{settings.TARGET_CHAIN}`\n"
                f"📊 **Tokens Fetched:** `{count}`\n"
                f"⏱ **Duration:** `{duration:.2f}s`\n"
                f"🕒 **Time:** `{timestamp}`"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
            await query.message.edit_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
            if settings.LOG_CHANNEL_ID:
                user_id = query.from_user.id
                log_msg = (
                    f"📡 **API Fetch Completed (Manual)**\n"
                    f"🔗 **Chain:** `{settings.TARGET_CHAIN}`\n"
                    f"📊 **Tokens Retrieved:** `{count}`\n"
                    f"🕒 **Time:** `{timestamp}`\n"
                    f"👤 **Triggered By:** `{user_id}`"
                )
                try:
                    await self.app.bot.send_message(chat_id=settings.LOG_CHANNEL_ID, text=log_msg, parse_mode='Markdown')
                except Exception as e:
                    log.error(f"Failed to log API fetch success: {e}")

        except Exception as e:
            log.error(f"Manual API Fetch Failed: {e}")
            timestamp = get_ist_time_str()
            
            fail_msg = (
                f"❌ **API Fetch Failed**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠ **Error:** `{str(e)}`\n"
                f"🕒 **Time:** `{timestamp}`"
            )
            keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
            await query.message.edit_text(fail_msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

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

    async def _render_watchlist(self, message):
        watchlist = state_manager.get_all()
        if not watchlist:
            text = "📈 **WATCHLIST**\n────────────────\nNo active tokens."
            keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        text = "📈 **ACTIVE ASSETS**\n────────────────\n"
        items = list(watchlist.items())[:8]
        for _, data in items:
            symbol = data.get('symbol', 'UNK')
            price = data.get('entry_price', 0)
            text += f"• **{symbol:<6}** | ${price:.4f}\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Prices", callback_data="watchlist_refresh")],
            [InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_refresh_watchlist(self, query):
        await query.answer("Fetching prices...")
        await query.message.edit_text("⏳ **Syncing Market Data...**")
        try:
            addresses = list(state_manager.get_all().keys())
            await self.api.get_pairs_bulk(addresses)
            await self._render_watchlist(query.message)
        except Exception:
            await query.message.edit_text("❌ **Sync Failed**", parse_mode='Markdown')
            await asyncio.sleep(1)
            await self._render_dashboard(query.message)

    async def _handle_watch_action(self, query, address):
        try:
            pairs = await self.api.get_pairs_bulk([address])
            if pairs:
                price = float(pairs[0].get('priceUsd', 0))
                symbol = pairs[0]['baseToken']['symbol']
                metadata = {"entry_price": price, "symbol": symbol, "chat_id": query.message.chat_id}
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
        except Exception:
            await query.answer("Error adding token")

    async def _handle_signal_refresh(self, query, address):
        await query.answer("Refreshing Signal Data...")
        try:
            pairs = await self.api.get_pairs_bulk([address])
            if not pairs:
                await query.answer("Token data unavailable", show_alert=True)
                return
            
            analysis = AnalysisEngine.analyze_token(pairs[0])
            if not analysis:
                await query.answer("Token no longer meets criteria", show_alert=True)
                return

            metrics = analysis.get('metrics', {})
            vol_h1 = metrics.get('volume_h1', 0)
            p_change = metrics.get('price_change_h1', 0)
            liq_fmt = f"${analysis.get('liquidity', 0):,.0f}"
            fdv_fmt = f"${analysis.get('fdv', 0):,.0f}"
            vol_fmt = f"${vol_h1:,.0f}"
            age_fmt = f"{analysis.get('age_hours', 0)}h"
            trend = "📈" if p_change >= 0 else "📉"
            refresh_time = get_ist_time_str("%H:%M:%S IST")
            
            msg = (
                f"💎 **GEM DETECTED** | {analysis['baseToken']['symbol']}\n"
                f"────────────────\n"
                f"💰 **Price:** `${analysis.get('priceUsd', '0')}`\n"
                f"💧 **Liquidity:** `{liq_fmt}`\n"
                f"📊 **FDV:** `{fdv_fmt}`\n"
                f"⏳ **Age:** `{age_fmt}`\n"
                f"🌊 **Vol (1H):** `{vol_fmt}`\n"
                f"{trend} **Change (1H):** `{p_change}%`\n"
                f"🎯 **Score:** `{analysis['risk']['score']}/100`\n"
                f"🐋 **Whale:** `{'YES 🚨' if analysis['whale']['detected'] else 'NO'}`\n"
                f"────────────────\n"
                f"🔄 **Refreshed:** `{refresh_time}`\n"
                f"`{analysis['address']}`"
            )
            keyboard = [
                [InlineKeyboardButton("👁 Watch", callback_data=f"watch:{analysis['address']}"),
                InlineKeyboardButton("🔄 Refresh", callback_data=f"signal_refresh:{analysis['address']}")],
                [InlineKeyboardButton("↗ DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{analysis['address']}")]
            ]
            await query.message.edit_text(text=msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            await query.answer("Refresh Failed", show_alert=True)

    async def _render_help(self, message):
        text = (
            "❓ **SYSTEM GUIDE**\n"
            "────────────────\n"
            "**Control Panel**\n"
            "• **Watchlist**: Track saved tokens.\n"
            "• **Refresh**: Force system metric sync.\n"
            "• **Settings**: Configure algorithm.\n"
            "• **API Request**: Manual trigger for token fetch.\n\n"
            "**Automated Signals**\n"
            "Bot scans for new tokens meeting 'Filters'.\n"
            "Signals are sent to the channel."
        )
        keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def broadcast_signal(self, analysis: dict):
        metrics = analysis.get('metrics', {})
        vol_h1 = metrics.get('volume_h1', 0)
        p_change = metrics.get('price_change_h1', 0)
        liq_fmt = f"${analysis.get('liquidity', 0):,.0f}"
        fdv_fmt = f"${analysis.get('fdv', 0):,.0f}"
        vol_fmt = f"${vol_h1:,.0f}"
        age_fmt = f"{analysis.get('age_hours', 0)}h"
        trend = "📈" if p_change >= 0 else "📉"
        detect_time = get_ist_time_str("%H:%M IST")
        
        msg = (
            f"💎 **GEM DETECTED** | {analysis['baseToken']['symbol']}\n"
            f"────────────────\n"
            f"💰 **Price:** `${analysis.get('priceUsd', '0')}`\n"
            f"💧 **Liquidity:** `{liq_fmt}`\n"
            f"📊 **FDV:** `{fdv_fmt}`\n"
            f"⏳ **Age:** `{age_fmt}`\n"
            f"🌊 **Vol (1H):** `{vol_fmt}`\n"
            f"{trend} **Change (1H):** `{p_change}%`\n"
            f"🎯 **Score:** `{analysis['risk']['score']}/100`\n"
            f"🐋 **Whale:** `{'YES 🚨' if analysis['whale']['detected'] else 'NO'}`\n"
            f"────────────────\n"
            f"🕒 **Detected:** `{detect_time}`\n"
            f"`{analysis['address']}`"
        )
        keyboard = [
            [InlineKeyboardButton("👁 Watch", callback_data=f"watch:{analysis['address']}"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"signal_refresh:{analysis['address']}")],
            [InlineKeyboardButton("↗ DexScreener", url=f"https://dexscreener.com/{settings.TARGET_CHAIN}/{analysis['address']}")]
        ]
        try:
            await self.app.bot.send_message(chat_id=settings.CHANNEL_ID, text=msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            log.error(f"Broadcast failed: {e}")

    async def send_exit_alert(self, address: str, pnl: float, reason: str):
        data = state_manager.get_all().get(address)
        if not data: return
        symbol = data.get('symbol', 'UNK')
        icon = "🚀" if pnl > 0 else "🛑"
        msg = f"🔔 **EXIT SIGNAL** {icon}\n────────────────\nAsset: **{symbol}**\nReason: {reason}\nPnL: **{pnl:+.2f}%**"
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
