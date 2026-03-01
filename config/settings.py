import yaml
import os
from pydantic_settings import BaseSettings
from typing import Dict, Any

class EnvSettings(BaseSettings):
    SIGNAL_BOT_TOKEN: str
    ALERT_BOT_TOKEN: str
    ADMIN_CHAT_ID: int
    CHANNEL_ID: int
    LOG_LEVEL: str = "INFO"
    POLL_INTERVAL: int = 5
    MAX_RETRIES: int = 3
    DEXSCREENER_API_URL: str

    class Config:
        env_file = ".env"
        extra = "ignore"

class ConfigManager:
    def __init__(self):
        self.env = EnvSettings()
        self.strategy = self._load_strategy()

    def _load_strategy(self) -> Dict[str, Any]:
        if not os.path.exists("strategy.yaml"):
            raise FileNotFoundError("strategy.yaml not found")
        with open("strategy.yaml", 'r') as f:
            return yaml.safe_load(f)

    @property
    def filters(self): return self.strategy.get('filters', {})
    
    @property
    def weights(self): return self.strategy.get('weights', {})
    
    @property
    def thresholds(self): return self.strategy.get('thresholds', {})

    @property
    def watch(self): return self.strategy.get('watch', {})
    
    @property
    def regime(self): return self.strategy.get('regime', {})

settings = ConfigManager()
