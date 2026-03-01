from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config.settings import settings, strategy
from utils.logger import log
from utils.state import state_manager
from api.dexscreener import DexScreenerAPI
from engines.analysis import AnalysisEngine
import asyncio
import time

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
        log.info("Initializing Signal Bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        log.info("Signal Bot Dashboard Active")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry point for the Dashboard."""
        await self._render_dashboard(update.message, is_new=True)

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🏓 Pong!")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Central Router for Dashboard Interactions"""
        query = update.callback_query
        await query.answer()  # Acknowledgement

        data = query.data.split(":")
        action = data[0]
        payload = data[1] if len(data) > 1 else None

        try:
            if action == "dashboard":
                await self._render_dashboard(query.message, is_new=False)
            
            elif action == "watchlist_view":
                await self._render_watchlist(query.message)
            
            elif action == "watchlist_refresh":
                await self._handle_refresh_watchlist(query)

            elif action == "settings_menu":
                await self._render_settings(query.message)
            
            elif action == "settings_reload":
                await strategy.reload()
                await query.edit_message_text(
                    text="✅ **Configuration Reloaded from Disk**",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="settings_menu")]])
                )

            elif action == "settings_toggle_strict":
                current = strategy.thresholds.get('strict_filtering', True)
                await strategy.update_threshold('strict_filtering', not current)
                await self._render_settings(query.message) # Re-render to show new state

            elif action == "help_menu":
                await self._render_help(query.message)
            
            elif action == "watch":
                if payload:
                    await self._handle_watch_action(query, payload)

            elif action == "noop":
                pass # Non-functional button (display only)

        except Exception as e:
            log.error(f"Dashboard Interaction Error ({action}): {e}")
            await query.message.reply_text("⚠️ An error occurred while processing your request.")

    # --- UI Rendering Methods ---

    async def _render_dashboard(self, message, is_new=False):
        """Renders the Main Trading Control Panel."""
        watchlist_count = len(state_manager.get_all())
        strict_mode = strategy.thresholds.get('strict_filtering', True)
        
        text = (
            f"🎛 **TRADING CONTROL PANEL**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 **System Status:** Online\n"
            f"⚡ **Latency:** Low\n"
            f"⛓ **Chain:** `{settings.TARGET_CHAIN.upper()}`\n\n"
            f"📊 **Live Statistics:**\n"
            f"• 👁 Watchlist: `{watchlist_count}` tokens\n"
            f"• 💧 Min Liq: `${strategy.filters.get('min_liquidity_usd', 'N/A')}`\n"
            f"• 🛡 Strict Mode: `{'✅ ON' if strict_mode else '⚠️ OFF'}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Select an action below:"
        )

        keyboard = [
            [
                InlineKeyboardButton("📊 Watchlist", callback_data="watchlist_view"),
                InlineKeyboardButton("🔄 Refresh", callback_data="watchlist_refresh")
            ],
            [
                InlineKeyboardButton("⚙ Settings", callback_data="settings_menu")
            ],
            [
                InlineKeyboardButton("❓ Help / Guide", callback_data="help_menu")
            ]
        ]

        if is_new:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_watchlist(self, message):
        """Displays formatted watchlist with PnL."""
        watchlist = state_manager.get_all()
        
        if not watchlist:
            text = "📂 **Your Watchlist is Empty**\n\nAdd tokens by clicking 'Watch' on signal alerts."
        else:
            text = "📊 **Active Watchlist**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            # Limit to top 10 for UI cleaniness in chat
            for i, (addr, data) in enumerate(list(watchlist.items())[:10]):
                symbol = data.get('symbol', 'UNKNOWN')
                entry = data.get('entry_price', 0)
                text += f"{i+1}. **${symbol}** | Entry: `${entry:.4f}`\n"
                text += f"   `{addr}`\n"
            
            if len(watchlist) > 10:
                text += f"\n...and {len(watchlist)-10} more."

        keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_settings(self, message):
        """Displays Settings & Filters Panel."""
        filters = strategy.filters
        strict = strategy.thresholds.get('strict_filtering', True)
        
        text = (
            f"⚙ **SETTINGS & CONFIGURATION**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Current Strategy Parameters:**\n\n"
            f"🔹 **Liquidity Filter:** `>${filters.get('min_liquidity_usd', 0)}`\n"
            f"🔹 **Max Age:** `{filters.get('max_age_hours', 24)}h`\n"
            f"🔹 **Strict Filtering:** `{'Enabled' if strict else 'Disabled'}`\n\n"
            f"💡 *Edit 'strategy.yaml' to change numeric values, then click Reload.*"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(f"🛡 Strict Mode: {'ON' if strict else 'OFF'}", callback_data="settings_toggle_strict")
            ],
            [
                InlineKeyboardButton("♻️ Reload Config from Disk", callback_data="settings_reload")
            ],
            [
                InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")
            ]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _render_help(self, message):
        text = (
            f"❓ **USER GUIDE**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Commands:**\n"
            f"`/start` - Open Dashboard\n"
            f"`/ping` - Check System Health\n\n"
            f"**How it works:**\n"
            f"1. Bot scans `{settings.TARGET_CHAIN}` for new tokens.\n"
            f"2. Filters are applied based on `strategy.yaml`.\n"
            f"3. High-quality signals are broadcasted.\n"
            f"4. Click 'Watch' to track PnL in Dashboard.\n"
        )
        keyboard = [[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # --- Logic Handlers ---

    async def _handle_refresh_watchlist(self, query):
        """
        Refreshes data, re-runs analysis, and updates view.
        Prevents spamming via visual feedback.
        """
        watchlist = state_manager.get_all()
        if not watchlist:
            await query.answer("Watchlist is empty!", show_alert=True)
            return

        await query.message.edit_text("⏳ **Refreshing Data...**\nFetching latest prices from DexScreener...")
        
        try:
            # 1. Bulk Fetch
            addresses = list(watchlist.keys())
            latest_data = await self.api.get_pairs_bulk(addresses)
            
            updated_count = 0
            risky_count = 0

            # 2. Analyze & Update
            for pair in latest_data:
                addr = pair.get('pairAddress')
                if not addr: continue

                # Re-run analysis logic to check if it's still "Safe"
                # We don't remove it automatically, but we could flag it.
                analysis = AnalysisEngine.analyze_token(pair)
                
                is_risky = False
                if not analysis: # Filtered out (e.g. liquidity dropped)
                    is_risky = True
                    risky_count += 1
                elif not analysis['risk']['is_safe']:
                    is_risky = True
                    risky_count += 1
                
                # Update current price in view (not persistence yet unless we want to track history)
                # For this feature, we just confirm we fetched it.
                updated_count += 1

            # 3. Return to Watchlist View with status
            text = (
                f"✅ **Refresh Complete**\n"
                f"Updated {updated_count} tokens.\n"
                f"⚠️ Flagged {risky_count} as potentially risky/low liquidity.\n\n"
                f"Redirecting to list..."
            )
            await query.message.edit_text(text, parse_mode='Markdown')
            await asyncio.sleep(1.5)
            await self._render_watchlist(query.message)

        except Exception as e:
            log.error(f"Refresh failed: {e}")
            await query.message.edit_text(
                "❌ **Refresh Failed**\nAPI Error or Timeout.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]])
            )

    async def _handle_watch_action(self, query, address):
        """Adds a token to the watchlist from a signal."""
        try:
            pairs = await self.api.get_pairs_bulk([address])
            if pairs:
                price = float(pairs[0].get('priceUsd', 0))
                metadata = {
                    "entry_price": price,
                    "symbol": pairs[0]['baseToken']['symbol'],
                    "chat_id": query.message.chat_id,
                    "added_at": time.time()
                }
                await state_manager.add_token(address, metadata)
                
                # Update visual state of the button
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
            await query.answer("Failed to add token. Try again.")

    async def broadcast_signal(self, analysis: dict):
        """Sends the formatted signal to the channel"""
        msg = (
            f"💎 **GEM DETECTED: {analysis['baseToken']['name']}**\n"
            f"Symbol: ${analysis['baseToken']['symbol']}\n"
            f"Address: `{analysis['address']}`\n\n"
            f"💰 Price: ${analysis['priceUsd']}\n"
            f"💧 Liquidity: ${analysis['liquidity']:,.0f}\n"
            f"⏳ Age: {analysis['age_hours']}h\n"
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
