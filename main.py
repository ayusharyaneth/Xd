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
processed_tokens = set()

async def pipeline_task():
    """
    Core Intelligence Loop: Fetches, Filters, Analyzes, Alerts.
    """
    log.info("Starting Pipeline...")
    while True:
        try:
            # 1. Self Defense
            if SystemHealth.check():
                await asyncio.sleep(10)
                continue

            # 2. Fetch Data (Search logic used for 'latest' simulation)
            pairs = await api.get_pairs_by_chain(settings.TARGET_CHAIN)
            
            for pair in pairs:
                addr = pair.get('pairAddress')
                
                # Dedup check
                if addr in processed_tokens:
                    continue
                
                # 3. Analyze
                result = AnalysisEngine.analyze_token(pair)
                
                if result:
                    # 4. Filter by Risk
                    if result['risk']['is_safe']:
                        log.info(f"Signal found: {result['baseToken']['symbol']}")
                        await signal_bot.broadcast_signal(result)
                        processed_tokens.add(addr)
                    else:
                        # Log risky tokens strictly for debug
                        log.debug(f"Skipped Risky: {result['baseToken']['symbol']} - Score: {result['risk']['score']}")

            # Cleanup processed cache to prevent memory leak
            if len(processed_tokens) > 10000:
                processed_tokens.clear()
            
            await asyncio.sleep(settings.POLL_INTERVAL)

        except Exception as e:
            log.error(f"Pipeline Iteration Error: {e}")
            await asyncio.sleep(5) # Backoff on error

async def watch_task():
    """
    Monitors active watchlist for PnL/Exit signals.
    """
    log.info("Starting Watch Monitor...")
    while True:
        try:
            watchlist = state_manager.get_all()
            if not watchlist:
                await asyncio.sleep(60)
                continue

            addresses = list(watchlist.keys())
            # Batch fetch
            current_data = await api.get_pairs_bulk(addresses)
            
            for pair in current_data:
                addr = pair['pairAddress']
                entry = watchlist[addr]
                curr_price = float(pair.get('priceUsd', 0))
                entry_price = entry['entry_price']

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

            await asyncio.sleep(60) # Check every minute
            
        except Exception as e:
            log.error(f"Watch Task Error: {e}")
            await asyncio.sleep(10)

async def main():
    # 0. Configure Logging (Dependency Injection)
    # This fixes the NameError by initializing the logger with settings explicitly
    setup_logger(settings.LOG_LEVEL)
    
    # 1. Initialize System
    log.info("Initializing System Components...")
    await state_manager.load()
    await api.start()
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
