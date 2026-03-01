import ujson
import asyncio
import os
from typing import Dict
from utils.logger import log

class StateManager:
    """
    Handles persistence of watched tokens to prevent data loss on restart.
    Uses a simple JSON file protected by an async lock.
    """
    def __init__(self, filename="watchlist.json"):
        self.filename = filename
        self._lock = asyncio.Lock()
        self.data: Dict[str, dict] = {}

    async def load(self):
        if not os.path.exists(self.filename):
            self.data = {}
            return
        
        async with self._lock:
            try:
                with open(self.filename, 'r') as f:
                    self.data = ujson.load(f)
                log.info(f"Loaded {len(self.data)} tokens from state.")
            except Exception as e:
                log.error(f"Failed to load state: {e}")
                self.data = {}

    async def save(self):
        async with self._lock:
            try:
                with open(self.filename, 'w') as f:
                    ujson.dump(self.data, f)
            except Exception as e:
                log.error(f"Failed to save state: {e}")

    async def add_token(self, address: str, metadata: dict):
        self.data[address] = metadata
        await self.save()

    async def remove_token(self, address: str):
        if address in self.data:
            del self.data[address]
            await self.save()

    def get_all(self):
        return self.data

state_manager = StateManager()
