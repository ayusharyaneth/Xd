import asyncio
import signal
import sys
from datetime import datetime
from config.settings import settings, strategy
from utils.logger import log, setup_logger
from utils.state import state_manager
from utils.helpers import get_ist_time_str
from api.dexscreener import DexScreenerAPI
from engines.analysis import AnalysisEngine
from bots.signal_bot import SignalBot
from bots.alert_bot import AlertBot
from system.supervisor import TaskSupervisor
from system.health import SystemHealth

# --- Global Instances ---
api = DexScreenerAPI()
alert_bot = AlertBot()
signal_bot = SignalBot(api)

# Runtime Cache
processed_tokens = set()

async def pipeline_task():
    """
    Core Intelligence Loop: Fetches, Filters, Analyzes, Alerts.
    Executes every POLL_INTERVAL seconds (Default 60s).
    """
    log.info(f"Starting Pipeline Task (Chain: {settings.TARGET_CHAIN})...")
    
    while True:
        try:
            # 1. Self Defense Check
            if SystemHealth.check():
                await asyncio.sleep(10)
                continue

            # 2. Fetch Data
            # log.debug("Fetching tokens from DexScreener...")
            start_time = datetime.now()
            pairs = await api.get_pairs_by_chain(settings.TARGET_CHAIN)
            
            if not pairs:
                log.debug("No pairs returned from API.")
                await asyncio.sleep(settings.POLL_INTERVAL)
                continue
            
            new_signals_count = 0
            dropped_count = 0
            
            for pair in pairs:
                addr = pair.get('pairAddress')
                if not addr: continue

                if addr in processed_tokens:
                    continue
                
                # 3. Analyze & Filter
                result = AnalysisEngine.analyze_token(pair)
                processed_tokens.add(addr) 
                
                if result:
                    if result['risk']['is_safe']:
                        log.info(f"Signal MATCH: {result['baseToken']['symbol']} ({addr})")
                        await signal_bot.broadcast_signal(result)
                        new_signals_count += 1
                    else:
                        # log.debug(f"Rejected (Risk): {result['baseToken']['symbol']}")
                        dropped_count += 1
                else:
                    dropped_count += 1
            
            # log.info(f"Pipeline Cycle: {len(pairs)} fetched | {new_signals_count} matched | {dropped_count} dropped")

            # 4. Log to Dedicated Channel
            if settings.LOG_CHANNEL_ID:
                timestamp = get_ist_time_str()
                log_msg = (
                    f"📡 **Auto Refresh Triggered**\n"
                    f"🔗 **Chain:** `{settings.TARGET_CHAIN}`\n"
                    f"📊 **Tokens Fetched:** `{len(pairs)}`\n"
                    f"🎯 **Matches:** `{new_signals_count}`\n"
                    f"🕒 **Time:** `{timestamp}`"
                )
                try:
                    await alert_bot.app.bot.send_message(chat_id=settings.LOG_CHANNEL_ID, text=log_msg, parse_mode='Markdown')
                except Exception as e:
                    log.error(f"Failed to log auto refresh: {e}")

            if len(processed_tokens) > 10000:
                processed_tokens.clear()
                log.info("Cleared processed tokens cache.")
            
            await asyncio.sleep(settings.POLL_INTERVAL)

        except asyncio.CancelledError:
            log.info("Pipeline task cancelled.")
            raise
        except Exception as e:
            log.error(f"Pipeline Iteration Error: {e}")
            if settings.LOG_CHANNEL_ID:
                try:
                    ts = get_ist_time_str()
                    await alert_bot.app.bot.send_message(
                        chat_id=settings.LOG_CHANNEL_ID, 
                        text=f"❌ **Auto Refresh Failed**\n⚠ Error: `{str(e)}`\n🕒 `{ts}`", 
                        parse_mode='Markdown'
                    )
                except: pass
            await asyncio.sleep(5) 

async def watch_task():
    """
    Monitors active watchlist for PnL/Exit signals.
    """
    log.info("Starting Watch Monitor Task...")
    while True:
        try:
            watchlist = state_manager.get_all()
            if not watchlist:
                await asyncio.sleep(30)
                continue

            # log.debug(f"Checking watchlist ({len(watchlist)} tokens)...")
            addresses = list(watchlist.keys())
            current_data = await api.get_pairs_bulk(addresses)
            
            for pair in current_data:
                addr = pair.get('pairAddress')
                if not addr or addr not in watchlist: continue

                entry = watchlist[addr]
                curr_price = float(pair.get('priceUsd', 0))
                entry_price = float(entry.get('entry_price', 0))

                if entry_price == 0: continue

                pnl_pct = ((curr_price - entry_price) / entry_price) * 100
                
                tp = strategy.thresholds.get('take_profit_percent', 100)
                sl = strategy.thresholds.get('stop_loss_percent', -25)

                if pnl_pct >= tp:
                    await signal_bot.send_exit_alert(addr, pnl_pct, "Take Profit 🚀")
                    await state_manager.remove_token(addr)
                elif pnl_pct <= sl:
                    await signal_bot.send_exit_alert(addr, pnl_pct, "Stop Loss 🛑")
                    await state_manager.remove_token(addr)

            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            log.info("Watch task cancelled.")
            raise
        except Exception as e:
            log.error(f"Watch Task Error: {e}")
            await asyncio.sleep(10)

async def main():
    setup_logger(settings.LOG_LEVEL)
    log.info("Initializing System...")
    
    try:
        await state_manager.load()
        await api.start()
        await alert_bot.initialize()
        await signal_bot.initialize()
    except Exception as e:
        log.critical(f"Failed to initialize system: {e}")
        return

    timestamp = get_ist_time_str()
    try:
        await alert_bot.send_system_alert(
            f"🟢 **Bot Status: ONLINE**\n"
            f"📡 Monitoring started on `{settings.TARGET_CHAIN}`\n"
            f"🕒 `{timestamp}`"
        )
    except Exception as e:
        log.error(f"Failed to send startup alert: {e}")

    stop_event = asyncio.Event()
    
    def handle_signal(sig):
        log.warning(f"Received system signal: {sig.name}")
        stop_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform != 'win32':
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    tasks = [
        asyncio.create_task(TaskSupervisor.create_task(pipeline_task(), "Pipeline")),
        asyncio.create_task(TaskSupervisor.create_task(watch_task(), "WatchMonitor"))
    ]

    log.success("All systems operational. Main loop running.")

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        log.warning("Main execution cancelled.")
    except Exception as e:
        log.critical(f"Fatal Runtime Error: {e}")
        try:
            await alert_bot.send_system_alert(f"🔥 **CRITICAL CRASH**\nException: `{str(e)}`")
        except: pass
    finally:
        log.info("Initiating Graceful Shutdown...")
        timestamp = get_ist_time_str()
        try:
            await alert_bot.send_system_alert(
                f"🔴 **Bot Status: OFFLINE**\n"
                f"⚠ Disconnected from VPS\n"
                f"🕒 `{timestamp}`"
            )
            await asyncio.sleep(1)
        except Exception as e:
            log.error(f"Failed to send offline alert: {e}")

        log.info("Stopping background tasks...")
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        log.info("Closing API sessions...")
        await api.close()

        log.info("Stopping Telegram bots...")
        await signal_bot.shutdown()
        await alert_bot.shutdown()
        
        log.success("Shutdown Complete. Goodbye.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
