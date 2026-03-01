import asyncio
import signal
from datetime import datetime
from config.settings import settings, strategy
from utils.logger import log, setup_logger
from utils.state import state_manager
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
    """
    log.info(f"Starting Pipeline Task (Chain: {settings.TARGET_CHAIN})...")
    
    while True:
        try:
            # 1. Self Defense Check
            if SystemHealth.check():
                await asyncio.sleep(10)
                continue

            # 2. Fetch Data
            pairs = await api.get_pairs_by_chain(settings.TARGET_CHAIN)
            
            if not pairs:
                log.debug("No pairs returned from API.")
                await asyncio.sleep(settings.POLL_INTERVAL)
                continue

            new_signals_count = 0
            
            for pair in pairs:
                addr = pair.get('pairAddress')
                if not addr: continue

                # Dedup check (Runtime)
                if addr in processed_tokens:
                    continue
                
                # 3. Analyze & Filter
                result = AnalysisEngine.analyze_token(pair)
                
                # Mark as processed to prevent re-calc
                processed_tokens.add(addr) 
                
                if result:
                    # 4. Filter by Risk
                    if result['risk']['is_safe']:
                        log.info(f"Signal found: {result['baseToken']['symbol']} ({addr})")
                        await signal_bot.broadcast_signal(result)
                        new_signals_count += 1
                    else:
                        log.debug(f"Filtered Risky: {result['baseToken']['symbol']}")
            
            if new_signals_count > 0:
                log.info(f"Processed batch. New Signals: {new_signals_count}")

            # Cleanup processed cache (Rolling window)
            if len(processed_tokens) > 10000:
                processed_tokens.clear()
                log.info("Cleared processed tokens cache.")
            
            await asyncio.sleep(settings.POLL_INTERVAL)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error(f"Pipeline Iteration Error: {e}")
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
                
                # Exit Logic
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
            raise
        except Exception as e:
            log.error(f"Watch Task Error: {e}")
            await asyncio.sleep(10)

async def main():
    # 0. Configure Logging
    setup_logger(settings.LOG_LEVEL)
    
    # 1. Initialize System Components
    log.info("Initializing System...")
    await state_manager.load()
    await api.start()
    
    # Initialize Bots (Starts polling/webhooks)
    await alert_bot.initialize()
    await signal_bot.initialize()

    # 2. Send Online Alert
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        await alert_bot.send_system_alert(
            f"🟢 **Bot Status: ONLINE**\n"
            f"📡 Monitoring started on `{settings.TARGET_CHAIN}`\n"
            f"🕒 `{timestamp}`"
        )
    except Exception as e:
        log.error(f"Failed to send startup alert: {e}")

    # 3. Setup Shutdown Signals
    stop_event = asyncio.Event()
    
    def handle_signal(sig):
        log.warning(f"Received system signal: {sig.name}")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    # 4. Launch Background Tasks
    tasks = [
        asyncio.create_task(TaskSupervisor.create_task(pipeline_task(), "Pipeline")),
        asyncio.create_task(TaskSupervisor.create_task(watch_task(), "WatchMonitor"))
    ]

    log.success("All systems operational. Main loop running.")

    # 5. Runtime Loop
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
        # 6. Graceful Shutdown Procedure
        log.info("Initiating Graceful Shutdown...")

        # A. Send Offline Alert (while connection is still active)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        try:
            log.info("Sending offline alert...")
            await alert_bot.send_system_alert(
                f"🔴 **Bot Status: OFFLINE**\n"
                f"⚠ Disconnected from VPS\n"
                f"🕒 `{timestamp}`"
            )
            # Brief pause to ensure message delivery
            await asyncio.sleep(1)
        except Exception as e:
            log.error(f"Failed to send offline alert: {e}")

        # B. Cancel Background Tasks
        log.info("Stopping background tasks...")
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # C. Close Network Sessions
        log.info("Closing API sessions...")
        await api.close()

        # D. Stop Bots
        log.info("Stopping Telegram bots...")
        await signal_bot.shutdown()
        await alert_bot.shutdown()
        
        log.success("Shutdown Complete. Goodbye.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass # Handled by signal handler, this prevents ugly traceback on forced exit
