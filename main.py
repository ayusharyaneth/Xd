import asyncio
import signal
import sys
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

# Deduplication set
processed_tokens = set()

async def pipeline_task():
    """
    Core Intelligence Loop: Fetches, Filters, Analyzes, Alerts.
    """
    log.info(f"Starting Pipeline Task (Chain: {settings.TARGET_CHAIN})...")
    
    while True:
        try:
            if SystemHealth.check():
                await asyncio.sleep(10)
                continue

            pairs = await api.get_pairs_by_chain(settings.TARGET_CHAIN)
            
            if not pairs:
                log.debug("No pairs returned from API.")
                await asyncio.sleep(settings.POLL_INTERVAL)
                continue

            new_signals_count = 0
            
            for pair in pairs:
                addr = pair.get('pairAddress')
                if not addr: continue

                if addr in processed_tokens:
                    continue
                
                result = AnalysisEngine.analyze_token(pair)
                
                # Deduplicate logic
                processed_tokens.add(addr) 
                
                if result and result['risk']['is_safe']:
                    log.info(f"Signal found: {result['baseToken']['symbol']} ({addr})")
                    await signal_bot.broadcast_signal(result)
                    new_signals_count += 1
            
            if new_signals_count > 0:
                log.info(f"Processed batch. New Signals: {new_signals_count}")

            if len(processed_tokens) > 10000:
                processed_tokens.clear()
                log.info("Cleared processed tokens cache.")
            
            await asyncio.sleep(settings.POLL_INTERVAL)

        except asyncio.CancelledError:
            log.info("Pipeline task cancelled.")
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

async def shutdown_sequence(tasks, reason="Signal Received"):
    """
    Perform a robust, graceful shutdown.
    """
    log.warning(f"Initiating Shutdown Sequence (Reason: {reason})...")

    # 1. Cancel Background Tasks first to stop new processing
    for t in tasks:
        if not t.done():
            t.cancel()
    
    # Wait briefly for tasks to acknowledge cancellation
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("Background tasks stopped.")

    # 2. Send Offline Alert (while Bots are still active)
    try:
        log.info("Sending offline alert...")
        await alert_bot.send_shutdown_alert(reason=reason)
    except Exception as e:
        log.error(f"Failed to send offline alert: {e}")

    # 3. Close API Sessions
    log.info("Closing API sessions...")
    await api.close()

    # 4. Shutdown Bots
    log.info("Shutting down bot instances...")
    await signal_bot.shutdown()
    await alert_bot.shutdown()

    log.success("Graceful shutdown complete. Bye!")

async def main():
    # 0. Configure Logging
    setup_logger(settings.LOG_LEVEL)
    
    # 1. Initialize System Components
    log.info("Initializing System...")
    try:
        await state_manager.load()
        await api.start()
        
        # Initialize Bots
        await alert_bot.initialize()
        await signal_bot.initialize()
        
        # Send Startup Alert
        await alert_bot.send_startup_alert()
        log.success("System Online & Monitoring.")

    except Exception as e:
        log.critical(f"Startup Failed: {e}")
        return

    # 2. Launch Background Tasks
    tasks = [
        asyncio.create_task(TaskSupervisor.create_task(pipeline_task(), "Pipeline")),
        asyncio.create_task(TaskSupervisor.create_task(watch_task(), "WatchMonitor"))
    ]

    # 3. Signal Handling Setup
    stop_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        sig_name = signal.Signals(sig).name
        log.warning(f"Signal {sig_name} received.")
        stop_event.set()

    # Register signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig, f=None: signal_handler(s, f))

    # 4. Main Loop
    try:
        # Wait until a signal is received
        await stop_event.wait()
    except asyncio.CancelledError:
        log.warning("Main loop cancelled.")
    except Exception as e:
        log.critical(f"Unexpected error in main loop: {e}")
        # If it crashes unexpectedly, we still try to run shutdown
        await shutdown_sequence(tasks, reason=f"Crash: {e}")
        return
    
    # 5. Graceful Exit
    await shutdown_sequence(tasks, reason="Manual Stop/Signal")

if __name__ == "__main__":
    try:
        # Check for Windows (dev) vs Linux (prod) for event loop policy if needed
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        asyncio.run(main())
    except KeyboardInterrupt:
        # This catches the interrupt if it happens during asyncio.run startup
        pass
