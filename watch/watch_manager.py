import asyncio
from utils.logger import logger
from engines.exit_engine import ExitAssistant

class WatchManager:
    def __init__(self):
        self.watched_tokens = {} # address -> pair_data

    def add_watch(self, address: str, pair_data: dict):
        self.watched_tokens[address] = pair_data
        logger.info(f"Added {address} to watch list.")

    def remove_watch(self, address: str):
        if address in self.watched_tokens:
            del self.watched_tokens[address]

    def get_count(self):
        return len(self.watched_tokens)

    async def monitor_loop(self, bot_callback):
        while True:
            for address, data in list(self.watched_tokens.items()):
                # Re-fetch data in real system. Using static data for exit check demo.
                exit_check = ExitAssistant.check_exit_conditions(data)
                if exit_check["should_exit"]:
                    await bot_callback(address, exit_check["reason"])
                    self.remove_watch(address)
            await asyncio.sleep(30)

watch_manager = WatchManager()
