#!/usr/bin/env python3
# ============================================================
# DEXSCREENER INTELLIGENCE SYSTEM - MAIN ORCHESTRATOR
# ============================================================

import asyncio
import signal
import sys
from typing import Optional, List, Dict, Any
import time

# Optional uvloop for performance
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("✓ Using uvloop for enhanced performance")
except ImportError:
    pass

from config.settings import get_config
from utils.logger import setup_logger, get_logger
from utils.helpers import get_timestamp, format_duration

# API Clients
from api.dexscreener import get_dexscreener_client, close_dexscreener_client, PairFilter
from api.rpc import get_rpc_client, close_rpc_client

# Intelligence Engines
from engines.risk import get_risk_engine
from engines.authenticity import get_authenticity_engine
from engines.developer import get_developer_engine
from engines.buy_quality import get_buy_quality_engine
from engines.whale import get_whale_engine
from engines.early_buyer import get_early_buyer_tracker
from engines.wallet_cluster import get_cluster_detector
from engines.capital_rotation import get_rotation_tracker
from engines.probability import get_probability_estimator
from engines.exit_engine import get_exit_assistant
from engines.ranking import get_ranking_engine
from engines.regime import get_regime_analyzer

# System Components
from watch.watch_manager import get_watch_manager
from system.health import get_health_checker
from system.self_defense import get_self_defense
from system.metrics import get_metrics_collector, get_performance_tracker

# Telegram Bots
from bots.signal_bot import get_signal_bot
from bots.alert_bot import get_alert_bot


class DexIntelligenceSystem:
    """Main orchestrator for the DexScreener Intelligence System"""
    
    def __init__(self):
        self.config = get_config()
        self.logger = setup_logger(
            log_level=self.config.settings.LOG_LEVEL,
            log_file=self.config.settings.LOG_FILE
        )
        
        # State
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._tasks: List[asyncio.Task] = []
        
        # Initialize components
        self._init_components()
    
    def _init_components(self):
        """Initialize all system components"""
        self.logger.info("Initializing DexScreener Intelligence System...")
        
        # API Clients
        self.dexscreener = get_dexscreener_client()
        self.rpc = get_rpc_client()
        
        # Intelligence Engines
        self.risk_engine = get_risk_engine()
        self.authenticity_engine = get_authenticity_engine()
        self.developer_engine = get_developer_engine()
        self.buy_quality_engine = get_buy_quality_engine()
        self.whale_engine = get_whale_engine()
        self.early_buyer_tracker = get_early_buyer_tracker()
        self.cluster_detector = get_cluster_detector()
        self.rotation_tracker = get_rotation_tracker()
        self.probability_estimator = get_probability_estimator()
        self.exit_assistant = get_exit_assistant()
        self.ranking_engine = get_ranking_engine()
        self.regime_analyzer = get_regime_analyzer()
        
        # System Components
        self.watch_manager = get_watch_manager()
        self.health_checker = get_health_checker()
        self.self_defense = get_self_defense()
        self.metrics = get_metrics_collector()
        self.performance = get_performance_tracker()
        
        # Telegram Bots
        self.signal_bot = get_signal_bot()
        self.alert_bot = get_alert_bot()
        
        # Filters
        self.pair_filter = PairFilter()
        
        self.logger.info("All components initialized")
    
    async def start(self):
        """Start the system"""
        self.logger.info("=" * 60)
        self.logger.info("Starting DexScreener Intelligence System")
        self.logger.info("=" * 60)
        
        self._running = True
        
        # Initialize bots
        signal_ok = await self.signal_bot.initialize()
        alert_ok = await self.alert_bot.initialize()
        
        if not signal_ok:
            self.logger.error("Failed to initialize signal bot")
        if not alert_ok:
            self.logger.error("Failed to initialize alert bot")
        
        # Send startup notification
        if alert_ok:
            await self.alert_bot.send_startup_notification()
        
        # Start main tasks
        self._tasks = [
            asyncio.create_task(self._main_loop(), name="main_loop"),
            asyncio.create_task(self._health_check_loop(), name="health_check"),
            asyncio.create_task(self._self_defense_loop(), name="self_defense"),
            asyncio.create_task(self._watch_update_loop(), name="watch_update"),
            asyncio.create_task(self._cleanup_loop(), name="cleanup"),
        ]
        
        # Wait for shutdown
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        
        await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("Shutting down system...")
        self._running = False
        
        # Send shutdown notification
        await self.alert_bot.send_shutdown_notification("manual")
        
        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Stop bots
        await self.signal_bot.stop()
        await self.alert_bot.stop()
        
        # Close API clients
        await close_dexscreener_client()
        await close_rpc_client()
        
        self.logger.info("System shutdown complete")
    
    async def _main_loop(self):
        """Main processing loop"""
        poll_interval = self.config.settings.POLL_INTERVAL_SECONDS
        
        while self._running:
            try:
                start_time = time.time()
                
                # Check safe mode
                if self.self_defense.should_reduce_features():
                    poll_interval = await self.self_defense.get_adjusted_poll_interval(
                        self.config.settings.POLL_INTERVAL_SECONDS
                    )
                
                # Fetch new pairs
                self.logger.debug("Fetching new pairs...")
                pairs = await self.dexscreener.get_new_pairs(limit=100)
                
                if pairs:
                    self.logger.info(f"Fetched {len(pairs)} pairs")
                    await self.metrics.increment_counter('tokens_fetched')
                    
                    # Update market regime
                    await self.regime_analyzer.update_metrics(pairs)
                    
                    # Apply filters
                    filtered = self.pair_filter.apply_all_filters(pairs)
                    self.logger.info(f"After filtering: {len(filtered)} pairs")
                    
                    # Process each pair
                    for pair in filtered:
                        await self._process_pair(pair)
                
                # Calculate processing time
                processing_time = (time.time() - start_time) * 1000
                await self.performance.record_operation_time('main_loop', processing_time)
                
                # Wait for next iteration
                await asyncio.sleep(poll_interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.exception(f"Error in main loop: {e}")
                await self.self_defense.record_api_call(False, 0)
                await asyncio.sleep(poll_interval)
    
    async def _process_pair(self, pair):
        """Process a single token pair through all engines"""
        
        try:
            start_time = time.time()
            
            # 1. Risk Scoring
            risk_result = await self.risk_engine.calculate_risk_score(pair)
            
            # Skip high-risk tokens
            if risk_result.total_score > 85:
                self.logger.debug(f"Skipping {pair.token_symbol} - too risky")
                return
            
            # 2. Volume Authenticity
            auth_result = await self.authenticity_engine.analyze_volume(pair)
            
            # Skip low authenticity
            if auth_result.score < 40:
                self.logger.debug(f"Skipping {pair.token_symbol} - low volume authenticity")
                return
            
            # 3. Developer Reputation
            dev_result = await self.developer_engine.analyze_developer(pair)
            
            # Skip blacklisted developers
            if dev_result.classification == 'blacklist':
                self.logger.warning(f"Skipping {pair.token_symbol} - blacklisted dev")
                return
            
            # 4. Buy Quality
            quality_result = await self.buy_quality_engine.analyze_buy_quality(pair)
            
            # 5. Whale Detection
            whales = await self.whale_engine.detect_whales(pair)
            whale_activity = len(whales) * 10 if whales else 0
            
            # 6. Early Buyer Tracking
            early_buyers = await self.early_buyer_tracker.track_early_buyers(pair)
            
            # 7. Rug Probability
            rug_prob = await self.probability_estimator.calculate_probability(
                pair,
                risk_score=risk_result.total_score,
                volume_authenticity=auth_result.score,
                developer_reputation=dev_result.score
            )
            
            # Skip high rug probability
            if rug_prob.probability > 0.6:
                self.logger.warning(f"Skipping {pair.token_symbol} - high rug risk")
                return
            
            # 8. Calculate composite score and rank
            ranking = await self.ranking_engine.rank_alert(
                pair=pair,
                risk_score=risk_result.total_score,
                volume_quality=auth_result.score,
                buy_quality=quality_result.score,
                developer_reputation=dev_result.score,
                whale_activity=whale_activity
            )
            
            if ranking:
                # Add to buffer
                added, top_alerts = await self.ranking_engine.add_to_buffer(ranking)
                
                if top_alerts:
                    # Send top alerts
                    for alert in top_alerts:
                        await self._send_ranked_alert(alert, pair, risk_result, auth_result)
                
                if added and not top_alerts:
                    # Store score for history
                    await self.ranking_engine.store_token_score(
                        pair.token_address,
                        ranking.composite_score,
                        ranking.component_scores
                    )
            
            # 9. Check for exit signals if watching
            if await self.watch_manager.is_watched(pair.token_address):
                exit_signals = await self.exit_assistant.check_exit_signals(
                    pair,
                    risk_score=risk_result.total_score,
                    rug_probability=rug_prob.probability
                )
                
                for signal in exit_signals:
                    await self.signal_bot.send_exit_alert(signal)
            
            # Record metrics
            processing_time = (time.time() - start_time) * 1000
            await self.performance.record_operation_time('process_pair', processing_time)
            await self.metrics.increment_counter('pairs_processed')
        
        except Exception as e:
            self.logger.exception(f"Error processing pair {pair.token_symbol}: {e}")
    
    async def _send_ranked_alert(self, alert, pair, risk_result, auth_result):
        """Send a ranked alert"""
        
        analysis = {
            'key_points': [
                f"Risk Level: {risk_result.level.value}",
                f"Volume Authenticity: {auth_result.score:.0f}/100",
                f"Natural Volume: {auth_result.natural_volume_ratio:.0%}"
            ] + risk_result.factors[:3]
        }
        
        await self.signal_bot.send_token_alert(
            pair=pair,
            risk_score=risk_result.total_score,
            volume_score=auth_result.score,
            composite_score=alert.composite_score,
            analysis=analysis
        )
        
        await self.ranking_engine.mark_alert_sent(pair.token_address)
        await self.metrics.increment_counter('alerts_sent')
    
    async def _health_check_loop(self):
        """Periodic health check loop"""
        interval = self.config.settings.HEALTH_CHECK_INTERVAL_SECONDS
        
        while self._running:
            try:
                result = await self.health_checker.run_health_checks(
                    dexscreener_client=self.dexscreener,
                    signal_bot=self.signal_bot,
                    alert_bot=self.alert_bot
                )
                
                if result.get('status') == 'critical':
                    self.logger.critical("Health check failed critically")
                    await self.alert_bot.send_system_alert(
                        title="CRITICAL HEALTH CHECK FAILURE",
                        message="System health check detected critical issues",
                        severity='critical',
                        notify_admin=True
                    )
                
                await asyncio.sleep(interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(interval)
    
    async def _self_defense_loop(self):
        """Self-defense monitoring loop"""
        interval = self.defense_config.monitoring.check_interval_seconds
        
        while self._running:
            try:
                result = await self.self_defense.check_system_health()
                
                if result.get('action') == 'safe_mode_activated':
                    self.logger.critical("Safe mode activated!")
                    
                    # Send alert
                    await self.alert_bot.send_self_defense_alert(
                        reason="System thresholds exceeded",
                        metrics=result.get('metrics', {}),
                        actions_taken=result.get('actions_taken', [])
                    )
                
                elif result.get('action') == 'recovery_completed':
                    self.logger.info("Recovery completed")
                    await self.alert_bot.send_recovery_alert(
                        component="Self Defense System",
                        recovery_time_seconds=0
                    )
                
                await asyncio.sleep(interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in self defense loop: {e}")
                await asyncio.sleep(interval)
    
    async def _watch_update_loop(self):
        """Watch mode update loop"""
        interval = self.config.settings.WATCH_UPDATE_INTERVAL_SECONDS
        
        while self._running:
            try:
                # Get all watched tokens
                watches = await self.watch_manager.get_watched_tokens()
                
                for watch in watches:
                    # Get fresh pair data
                    pairs = await self.dexscreener.get_token_pairs(watch.token_address)
                    
                    if pairs:
                        pair = pairs[0]  # Use first pair
                        
                        # Calculate risk
                        risk_result = await self.risk_engine.calculate_risk_score(pair)
                        
                        # Update watch
                        alert = await self.watch_manager.update_watch(
                            watch.token_address,
                            pair,
                            risk_result.total_score
                        )
                        
                        if alert:
                            await self.signal_bot.send_watch_update(watch, alert.message)
                
                await asyncio.sleep(interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in watch update loop: {e}")
                await asyncio.sleep(interval)
    
    async def _cleanup_loop(self):
        """Periodic cleanup loop"""
        while self._running:
            try:
                # Run cleanup every hour
                await asyncio.sleep(3600)
                
                self.logger.info("Running periodic cleanup...")
                
                # Cleanup all components
                await self.whale_engine.cleanup()
                await self.early_buyer_tracker.cleanup_old_data()
                await self.cluster_detector.cleanup()
                await self.rotation_tracker.cleanup()
                await self.probability_estimator.cleanup()
                await self.exit_assistant.cleanup()
                await self.ranking_engine.cleanup()
                await self.watch_manager.cleanup_expired()
                await self.metrics.cleanup_old_data()
                
                self.logger.info("Cleanup completed")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")
    
    def request_shutdown(self):
        """Request graceful shutdown"""
        self.logger.info("Shutdown requested")
        self._shutdown_event.set()


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    print("\nShutdown signal received...")
    if system:
        system.request_shutdown()


# Global system instance
system: Optional[DexIntelligenceSystem] = None


async def main():
    """Main entry point"""
    global system
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start system
    system = DexIntelligenceSystem()
    
    try:
        await system.start()
    except Exception as e:
        logger = get_logger()
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
