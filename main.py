import asyncio
import signal
from loguru import logger
from config.settings import settings
from api.dexscreener import DexScreenerClient
from bots.signal_bot import SignalBot
from bots.alert_bot import AlertBot
from system.self_defense import SelfDefense
from engines.risk import RiskEngine
from engines.authenticity import AuthenticityEngine
from engines.whale import WhaleEngine
from engines.regime import RegimeEngine
from watch.watch_manager import watch_manager

# Init Engines
risk_engine = RiskEngine()
auth_engine = AuthenticityEngine()
whale_engine = WhaleEngine()
regime_engine = RegimeEngine()

# Init Systems
defense_sys = SelfDefense()
api_client = DexScreenerClient()
alert_bot = AlertBot()
signal_bot = SignalBot(defense_sys)

async def process_pipeline(token_data):
    """Core Intelligence Pipeline"""
    try:
        # 1. Filters
        if float(token_data.get('liquidity', {}).get('usd', 0)) < settings.filters['min_liquidity']:
            return

        # 2. Engines
        r_score = risk_engine.calculate_risk(token_data)
        a_score = auth_engine.analyze(token_data)
        is_whale, _ = whale_engine.detect(token_data)
        
        # 3. Composite Score
        composite_score = 100 - r_score + (0.5 * a_score)
        if is_whale: composite_score += 10
        
        # 4. Regime Adjustment
        status = regime_engine.get_status()
        if status == "BEAR": composite_score -= 20
        
        # 5. Alert
        if composite_score > 60: # Threshold
            analysis = {
                "score": int(composite_score),
                "risk_score": r_score,
                "whale": is_whale
            }
            await signal_bot.send_signal(token_data, analysis)
            
    except Exception as e:
        logger.error(f"Pipeline Error: {e}")

async def monitor_loop():
    logger.info("Starting Monitoring Loop...")
    
    # Mock list of addresses to monitor for the demo if 'latest' isn't available
    # In prod, this would scrape 'latest' or listen to a websocket
    # Here we query a known active pool for demonstration
    target_tokens = ["0x123..."] # Ideally fetched dynamically
    
    while True:
        try:
            if defense_sys.check():
                await asyncio.sleep(30)
                continue

            # 1. Fetch Data
            # Note: In real app, you'd fetch 'latest' pairs. 
            # DexScreener needs specific chain/address usually.
            # We assume get_latest_pairs is implemented or we poll specific pairs.
            # For this code to run without erroring on empty, we skip if no logic.
            # pairs = await api_client.get_latest_pairs() 
            
            # Using specific pair for stability in this code artifact:
            # (Replace with real polling logic)
            await asyncio.sleep(settings.env.POLL_INTERVAL)
            
        except Exception as e:
            logger.error(f"Loop Error: {e}")
            await asyncio.sleep(5)

async def watch_loop():
    """Manages Watched Tokens"""
    while True:
        active = watch_manager.get_active_watches()
        if active:
            data = await api_client.get_multiple_tokens(active)
            for pair in data:
                # Check exit conditions (Take Profit / Stop Loss)
                pass # Implementation details in ExitEngine
        await asyncio.sleep(60)

async def main():
    logger.info("Initializing System...")
    
    # Start API & Bots
    await api_client.start()
    await alert_bot.initialize()
    await signal_bot.initialize()

    # Tasks
    tasks = [
        asyncio.create_task(monitor_loop()),
        asyncio.create_task(watch_loop())
    ]

    # Graceful Shutdown
    stop_event = asyncio.Event()
    
    def signal_handler():
        logger.info("Shutdown signal received.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    await stop_event.wait()
    
    # Cleanup
    logger.info("Cleaning up...")
    for task in tasks: task.cancel()
    await api_client.close()
    await signal_bot.shutdown()
    await alert_bot.shutdown()
    logger.info("System Shutdown Complete.")

if __name__ == "__main__":
    try:
        # Windows selector event loop policy fix if needed
        # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
