import yaml
import os
from pydantic_settings import BaseSettings
from typing import List, Dict, Any

class Settings(BaseSettings):
    SIGNAL_BOT_TOKEN: str
    ALERT_BOT_TOKEN: str
    ADMIN_CHAT_IDS: str
    CHANNEL_ID: int
    LOG_LEVEL: str = "INFO"
    POLL_INTERVAL: int = 10  # Increased to prevent rate limits
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
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists("strategy.yaml"):
            # Safe defaults if file missing
            return {
                "filters": {
                    "min_liquidity_usd": 1000,
                    "max_age_hours": 24  # Critical to prevent flooding old tokens
                }, 
                "weights": {}, 
                "thresholds": {}
            }
        with open("strategy.yaml", "r") as f:
            return yaml.safe_load(f)

    @property
    def filters(self): return self._data.get('filters', {})
    @property
    def weights(self): return self._data.get('weights', {})
    @property
    def thresholds(self): return self._data.get('thresholds', {})

# Singletons
settings = Settings()
strategy = StrategyConfig()
