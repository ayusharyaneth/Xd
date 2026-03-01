import asyncio
import time
from typing import Dict, Any, List
from utils.logger import logger
from engines.exit_engine import ExitAssistant
from config.settings import settings

class WatchManager:
    def __init__(self):
        # token_address -> {"data": pair_data, "added_at": ts, "expires_at": ts}
        self._watched_tokens: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def add_watch(self, address: str, pair_data: dict):
        async with self._lock:
            now = time.time()
            expiry = now + settings.WATCH_EXPIRY_SECONDS
            self._watched_tokens[address] = {
                "data": pair_data,
                "added_at": now,
                "expires_at": expiry,
                "escalated": False  # prevent multiple escalations for same watch
            }
            logger.info(f"Added {address} to watch list. Expires in {settings.WATCH_EXPIRY_SECONDS}s")

    async def remove_watch(self, address: str):
        async with self._lock:
            if address in self._watched_tokens:
                del self._watched_tokens[address]
                logger.info(f"Removed {address} from watch list.")

    async def list_watches(self) -> List[Dict[str, Any]]:
        async with self._lock:
            result = []
            now = time.time()
            for addr, info in list(self._watched_tokens.items()):
                remaining = max(0, int(info["expires_at"] - now))
                result.append({
                    "address": addr,
                    "added_at": info["added_at"],
                    "expires_in": remaining,
                    "escalated": info.get("escalated", False),
                    "data": info.get("data", {})
                })
            return result

    async def count(self) -> int:
        async with self._lock:
            return len(self._watched_tokens)

    async def monitor_loop(self, bot_callback):
        """
        Periodically check watched tokens for exit conditions and expiry.
        bot_callback: coroutine callable(token_address: str, reason: str)
        """
        logger.info("WatchManager monitor loop started.")
        while True:
            try:
                now = time.time()
                # Make a snapshot to iterate without holding lock long
                async with self._lock:
                    items = list(self._watched_tokens.items())
                for address, info in items:
                    # if expired remove
                    if info["expires_at"] <= now:
                        await self.remove_watch(address)
                        continue

                    # perform exit checks
                    pair_data = info.get("data", {})
                    exit_check = ExitAssistant.check_exit_conditions(pair_data)
                    # escalate if should_exit and not yet escalated
                    if exit_check["should_exit"] and not info.get("escalated", False):
                        # mark escalated
                        async with self._lock:
                            if address in self._watched_tokens:
                                self._watched_tokens[address]["escalated"] = True
                        # call bot callback
                        try:
                            await bot_callback(address, exit_check["reason"])
                        except Exception as e:
                            logger.error(f"Watch monitor bot callback error for {address}: {e}")
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                logger.info("WatchManager.monitor_loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in WatchManager monitor loop: {e}")
                await asyncio.sleep(5)

watch_manager = WatchManager()
