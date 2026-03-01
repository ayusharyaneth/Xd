import asyncio
from utils.logger import logger
from engines.exit_engine import ExitAssistant
from typing import Dict, Any, Optional

class WatchManager:
    def __init__(self):
        self.watched_tokens: Dict[str, dict] = {}  # address -> full pair_data
        self._last_alert_time: Dict[str, float] = {}  # Cooldown tracking
        self.cooldown_seconds = 300  # 5 minutes between alerts for same token

    def add_watch(self, address: str, pair_data: dict):
        """Add or update a token in the watchlist"""
        self.watched_tokens[address] = pair_data
        logger.info(f"Added/Updated {address} in watch list. Total watches: {len(self.watched_tokens)}")

    def remove_watch(self, address: str):
        """Remove a token from watchlist"""
        if address in self.watched_tokens:
            del self.watched_tokens[address]
            if address in self._last_alert_time:
                del self._last_alert_time[address]
            logger.info(f"Removed {address} from watch list.")

    def is_watched(self, address: str) -> bool:
        """Check if a token is currently being watched"""
        return address in self.watched_tokens

    def get_count(self) -> int:
        """Get number of watched tokens"""
        return len(self.watched_tokens)

    def get_watchlist_summary(self) -> list:
        """Get formatted list of watched tokens for display"""
        summary = []
        for address, data in self.watched_tokens.items():
            symbol = data.get("baseToken", {}).get("symbol", "UNKNOWN")
            price = data.get("priceUsd", "N/A")
            summary.append({
                "address": address,
                "symbol": symbol,
                "price": price
            })
        return summary

    def can_alert(self, address: str) -> bool:
        """Check if enough time has passed since last alert for this token"""
        import time
        current_time = time.time()
        if address in self._last_alert_time:
            if current_time - self._last_alert_time[address] < self.cooldown_seconds:
                return False
        self._last_alert_time[address] = current_time
        return True

    async def monitor_loop(self, exit_callback):
        """Monitor watched tokens for exit conditions"""
        while True:
            try:
                current_watches = list(self.watched_tokens.items())
                for address, data in current_watches:
                    # Check exit conditions using current data
                    exit_check = ExitAssistant.check_exit_conditions(data)
                    if exit_check["should_exit"]:
                        # Check cooldown before sending exit alert
                        if self.can_alert(address):
                            await exit_callback(address, exit_check["reason"])
                        # Don't remove automatically, let user decide via button or manual removal
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in watch monitor loop: {e}")
                await asyncio.sleep(5)

watch_manager = WatchManager()
