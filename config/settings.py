import yaml
import os
from pydantic_settings import BaseSettings
from typing import List, Dict, Any
import asyncio

class Settings(BaseSettings):
    SIGNAL_BOT_TOKEN: str
    ALERT_BOT_TOKEN: str
    ADMIN_CHAT_IDS: str
    CHANNEL_ID: int
    LOG_LEVEL: str = "INFO"
    POLL_INTERVAL: int = 10
    TARGET_CHAIN: str = "solana"

    class Config:
        env_file = ".env"
        extra = "ignore"

    def get_admins(self) -> List[int]:
        try:
            return [int(x.strip()) for x in self.ADMIN_CHAT_IDS.split(",") if x.strip()]
        except:
            return []

class StrategyConfig:
    def __init__(self):
        self.filepath = "strategy.yaml"
        self._lock = asyncio.Lock()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.filepath):
            return {
                "filters": {
                    "min_liquidity_usd": 1000,
                    "max_age_hours": 24
                }, 
                "weights": {}, 
                "thresholds": {
                    "risk_alert_level": 70,
                    "strict_filtering": True
                }
            }
        try:
            with open(self.filepath, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading strategy: {e}")
            return {}

    async def reload(self):
        """Hot-reloads the configuration from disk."""
        async with self._lock:
            self._data = self._load()

    async def save(self):
        """Persists current in-memory configuration to disk."""
        async with self._lock:
            try:
                with open(self.filepath, "w") as f:
                    yaml.dump(self._data, f, default_flow_style=False)
            except Exception as e:
                print(f"Error saving strategy: {e}")

    async def update_threshold(self, key: str, value: Any):
        """Updates a specific threshold setting safely."""
        if 'thresholds' not in self._data:
            self._data['thresholds'] = {}
        self._data['thresholds'][key] = value
        await self.save()

    @property
    def filters(self): return self._data.get('filters', {})
    @property
    def weights(self): return self._data.get('weights', {})
    @property
    def thresholds(self): return self._data.get('thresholds', {})

# Singletons
settings = Settings()
strategy = StrategyConfig()
