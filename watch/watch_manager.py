import asyncio
import time
from utils.logger import logger
from engines.exit_engine import ExitAssistant
from typing import Dict, Any, Optional, Callable

class WatchManager:
    def __init__(self):
        self.watched_tokens: Dict[str, dict] = {}
        self._last_alert_time: Dict[str, float] = {}
        self.cooldown_seconds = 300

    def add_watch(self, address: str, pair_data: dict):
        self.watched_tokens[address] = pair_data
        logger.info(f"Added {address} to watch list. Total: {len(self.watched_tokens)}")

    def remove_watch(self, address: str):
        if address in self.watched_tokens:
            del self.watched_tokens[address]
            self._last_alert_time.pop(address, None)
            logger.info(f"Removed {address} from watch list.")

    def is_watched(self, address: str) -> bool:
        return address in self.watched_tokens

    def get_count(self) -> int:
        return len(self.watched_tokens)

    def can_alert(self, address: str) -> bool:
        current_time = time.time()
        if address in self._last_alert_time:
            time_since = current_time - self._last_alert_time[address]
            if time_since < self.cooldown_seconds:
                remaining = int(self.cooldown_seconds - time_since)
                logger.debug(f"Cooldown active for {address}: {remaining}s remaining")
                return False
        self._last_alert_time[address] = current_time
        return True

    async def monitor_loop(self, exit_callback: Callable):
        while True:
            try:
                current_watches = list(self.watched_tokens.items())
                for address, data in current_watches:
                    # TODO: Refresh data from API here for real-time prices
                    exit_check = ExitAssistant.check_exit_conditions(data)
                    if exit_check["should_exit"] and self.can_alert(address):
                        await exit_callback(address, exit_check["reason"])
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watch monitor error: {e}")
                await asyncio.sleep(5)

watch_manager = WatchManager()
