import asyncio
from datetime import datetime
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

# Minimum score threshold to avoid spam (configurable)
MIN_SCORE_THRESHOLD = 70.0

async def core_loop():
    """Main intelligence loop with smart deduplication"""
    logger.info("Starting Core Intelligence Loop...")
    
    while True:
        try:
            # Self-defense check
            if self_defense.check_and_activate():
                await alert_bot.send_alert("Safe Mode Activated due to high error rates or latency.")
                await asyncio.sleep(60)
                continue

            pairs = await dex_api.fetch_latest_pairs()
            processed_count = 0
            
            for pair in pairs:
                try:
                    # Get token identifier
                    address = pair.get("baseToken", {}).get("address", "")
                    if not address:
                        continue
                    
                    # Stage 1: Risk Filter (Fast rejection)
                    risk_data = RiskEngine.evaluate(pair)
                    if not risk_data["passed"]:
                        continue
                    
                    # Stage 2: Deep Intelligence Analysis
                    auth_score = AuthenticityEngine.evaluate(pair)
                    dev_data = DeveloperEngine.evaluate(pair)
                    cluster_score = WalletClusterEngine.detect(pair)
                    
                    # Calculate rug probability (lower is better)
                    rug_prob = RugProbabilityEstimator.estimate(
                        risk_data, auth_score, dev_data["reputation_score"], cluster_score
                    )
                    
                    # Only proceed if quality is high enough (rug_prob < 50 means good)
                    if rug_prob >= 50:
                        continue
                    
                    # Calculate composite score
                    whale_data = WhaleEngine.detect(pair)
                    base_score = (100 - rug_prob)
                    whale_bonus = 15 if whale_data["whale_detected"] else 0
                    final_score = min(100.0, base_score + whale_bonus)
                    
                    # STRICT CRITERIA CHECK: Only alert if meets threshold
                    if final_score < MIN_SCORE_THRESHOLD:
                        continue
                    
                    # Check if this is a watched token (refresh) or new detection
                    is_watched = watch_manager.is_watched(address)
                    
                    # Cooldown check to prevent spam
                    if not watch_manager.can_alert(address):
                        continue
                    
                    # Send appropriate message type
                    await signal_bot.send_signal(pair, final_score, is_update=is_watched)
                    processed_count += 1
                    
                    # If it's a good new token, optionally add to ranking buffer for batch alerts
                    if not is_watched:
                        ranking_engine.add_alert(pair, final_score)
                        
                except Exception as e:
                    logger.error(f"Error processing pair: {e}")
                    continue
            
            # Process any batch rankings if needed (optional, for top N summary)
            top_tokens = ranking_engine.get_top_n(3)
            if top_tokens and not is_watched:  # Only send batch summary for new discoveries
                logger.info(f"Batch processed {len(top_tokens)} top tokens")
            
            logger.info(f"Loop completed. Processed {processed_count} high-quality signals.")
            await asyncio.sleep(settings.POLL_INTERVAL)
            
        except asyncio.CancelledError:
            logger.info("Core loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in core loop: {e}")
            await alert_bot.send_alert(f"Core loop exception: {str(e)}")
            await asyncio.sleep(5)

async def main():
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop for optimized performance")
    except ImportError:
        logger.info("Using standard asyncio event loop")

    logger.info("Initializing DexScreener Intelligence System...")
    
    # Initialize bots
    await signal_bot.start_bot()
    await alert_bot.start_bot()
    
    # Create concurrent tasks
    tasks = [
        asyncio.create_task(core_loop(), name="core_intelligence"),
        asyncio.create_task(watch_manager.monitor_loop(signal_bot.send_watch_alert), name="watch_monitor")
    ]
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await alert_bot.send_alert(f"Fatal system error: {str(e)}")
    finally:
        # Cleanup
        logger.info("Initiating graceful shutdown...")
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        await dex_api.close()
        await signal_bot.stop_bot()
        await alert_bot.stop_bot()
        logger.info("System shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
