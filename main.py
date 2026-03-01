import asyncio
from utils.logger import logger
from config.settings import settings
from api.dexscreener import dex_api
from engines.risk import RiskEngine
from engines.authenticity import AuthenticityEngine
from engines.developer import DeveloperEngine
from engines.buy_quality import BuyQualityEngine
from engines.whale import WhaleEngine
from engines.wallet_cluster import WalletClusterEngine
from engines.probability import RugProbabilityEstimator
from engines.ranking import ranking_engine
from system.self_defense import self_defense
from bots.signal_bot import signal_bot
from bots.alert_bot import alert_bot
from watch.watch_manager import watch_manager

async def core_loop():
    logger.info("Starting Core Intelligence Loop...")
    while True:
        try:
            if self_defense.check_and_activate():
                await alert_bot.send_alert("Safe Mode Activated due to high error rates or latency.")
                await asyncio.sleep(60)
                continue

            pairs = await dex_api.fetch_latest_pairs()
            
            for pair in pairs:
                # Stage 1: Risk Filter
                risk_data = RiskEngine.evaluate(pair)
                if not risk_data["passed"]:
                    continue
                    
                # Stage 2: Deep Intelligence
                auth_score = AuthenticityEngine.evaluate(pair)
                dev_data = DeveloperEngine.evaluate(pair)
                cluster_score = WalletClusterEngine.detect(pair)
                
                rug_prob = RugProbabilityEstimator.estimate(risk_data, auth_score, dev_data["reputation_score"], cluster_score)
                
                if rug_prob < 50.0: # Good quality token threshold
                    whale_data = WhaleEngine.detect(pair)
                    score = (100 - rug_prob) + (10 if whale_data["whale_detected"] else 0)
                    ranking_engine.add_alert(pair, score)

            # Process top ranked tokens
            top_tokens = ranking_engine.get_top_n(3)
            for item in top_tokens:
                token = item["data"]
                symbol = token.get("baseToken", {}).get("symbol", "UNKNOWN")
                address = token.get("baseToken", {}).get("address", "UNKNOWN")
                price = token.get("priceUsd", "0")
                
                msg = (
                    f"🚀 **NEW ALPHA DETECTED** 🚀\n"
                    f"**Symbol:** {symbol}\n"
                    f"**Address:** `{address}`\n"
                    f"**Price:** {price} USD\n"
                    f"**Score:** {item['score']:.2f}/100\n"
                )
                await signal_bot.send_signal(msg, address)

            await asyncio.sleep(settings.POLL_INTERVAL)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in core loop: {e}")
            await alert_bot.send_alert(f"Core loop exception: {e}")
            await asyncio.sleep(5)

async def main():
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

    logger.info("Initializing DexScreener Intelligence System...")
    
    # Start Bots
    await signal_bot.start()
    
    # Create Tasks
    tasks = [
        asyncio.create_task(core_loop()),
        asyncio.create_task(watch_manager.monitor_loop(signal_bot.send_watch_alert))
    ]
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    finally:
        for task in tasks:
            task.cancel()
        await dex_api.close()
        await signal_bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
      
