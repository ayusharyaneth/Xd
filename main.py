import asyncio
import signal
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

# Using a set for processed tokens is good for runtime deduplication,
# but ideally, this should persist or we should rely on strict age filtering.
processed_tokens = set()

async def pipeline_task():
    """
    Core Intelligence Loop: Fetches, Filters, Analyzes, Alerts.
    """
    log.info(f"Starting Pipeline Task (Chain: {settings.TARGET_CHAIN})...")
    
    # Pre-load known tokens to prevent startup flooding if needed, 
    # but strictly relies on Age Filter now.
    
    while True:
        try:
            # 1. Self Defense Check
            if SystemHealth.check():
                await asyncio.sleep(10)
                continue

            # 2. Fetch Data
            # Note: The API likely uses a search query. 
            # This returns 'relevant' tokens, which might be old.
            # The AnalysisEngine MUST filter by Age.
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
                # This now includes the strict Age Check
                result = AnalysisEngine.analyze_token(pair)
                
                # Mark as processed regardless of result to avoid re-calculating bad tokens
                processed_tokens.add(addr) 
                
                if result:
                    # 4. Filter by Risk (Double check)
                    if result['risk']['is_safe']:
                        log.info(f"Signal found: {result['baseToken']['symbol']} ({addr}) - Age: {result['age_hours']}h")
                        await signal_bot.broadcast_signal(result)
                        new_signals_count += 1
                    else:
                        log.debug(f"Filtered Risky/Old: {result['baseToken']['symbol']}")
            
            if new_signals_count > 0:
                log.info(f"Processed batch. New Signals: {new_signals_count}")

            # Cleanup processed cache to prevent memory leak
            # We keep it large enough to cover the API's return window
            if len(processed_tokens) > 10000:
                processed_tokens.clear()
                log.info("Cleared processed tokens cache.")
            
            await asyncio.sleep(settings.POLL_INTERVAL)

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
            # Batch fetch updates
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
            
        except Exception as e:
            log.error(f"Watch Task Error: {e}")
            await asyncio.sleep(10)

async def main():
    # 0. Configure Logging
    setup_logger(settings.LOG_LEVEL)
    
    # 1. Initialize System
    log.info("Initializing System Components...")
    await state_manager.load()
    await api.start()
    
    # Initialize Bots (This starts the internal polling tasks)
    await alert_bot.initialize()
    await signal_bot.initialize()

    # 2. Setup Shutdown Signal
    stop_event = asyncio.Event()
    def signal_handler():
        log.warning("Shutdown signal received...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # 3. Launch Background Tasks via Supervisor
    tasks = [
        asyncio.create_task(TaskSupervisor.create_task(pipeline_task(), "Pipeline")),
        asyncio.create_task(TaskSupervisor.create_task(watch_task(), "WatchMonitor"))
    ]

    await alert_bot.send_system_alert("System Online 🟢")
    log.success("All systems operational. Waiting for signals...")
    
    # 4. Wait for shutdown
    await stop_event.wait()

    # 5. Cleanup
    log.info("Shutting down services...")
    for t in tasks: t.cancel()
    await api.close()
    await signal_bot.shutdown()
    await alert_bot.shutdown()
    log.success("Shutdown Complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
