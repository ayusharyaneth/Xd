import yaml
import os
import asyncio
from pydantic_settings import BaseSettings
from typing import List, Dict, Any, Union, Optional
from pydantic import Field, field_validator

class Settings(BaseSettings):
    SIGNAL_BOT_TOKEN: str
    ALERT_BOT_TOKEN: str
    ADMIN_IDS: str
    CHANNEL_ID: int
    LOG_CHANNEL_ID: Optional[int] = Field(default=None, description="Channel ID for security logs")
    LOG_LEVEL: str = "INFO"
    POLL_INTERVAL: int = 15
    TARGET_CHAIN: str = "solana"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def admin_list(self) -> List[int]:
        """Parses comma-separated ADMIN_IDS string into a list of integers."""
        if not self.ADMIN_IDS:
            return []
        try:
            return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]
        except ValueError:
            return []

    # Alias method to support existing calls to get_admins()
    def get_admins(self) -> List[int]:
        return self.admin_list

    @field_validator("LOG_CHANNEL_ID", mode="before")
    @classmethod
    def validate_log_channel(cls, v):
        if v == "" or v is None:
            return None
        return int(v)

class StrategyConfig:
    def __init__(self):
        self.filepath = "strategy.yaml"
        self._lock = asyncio.Lock()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        """Loads strategy safely with defaults."""
        defaults = {
            "filters": {
                "min_liquidity_usd": 1000,
                "max_age_hours": 24,
                "min_volume_h1": 500
            }, 
            "weights": {
                "volume_authenticity": 1.5
            }, 
            "thresholds": {
                "risk_alert_level": 70,
                "strict_filtering": True,
                "take_profit_percent": 100,
                "stop_loss_percent": -25
            }
        }
        
        if not os.path.exists(self.filepath):
            return defaults
            
        try:
            with open(self.filepath, "r") as f:
                loaded = yaml.safe_load(f) or {}
                for section in defaults:
                    if section not in loaded:
                        loaded[section] = defaults[section]
                    else:
                        for key, val in defaults[section].items():
                            if key not in loaded[section]:
                                loaded[section][key] = val
                return loaded
        except Exception as e:
            print(f"Error loading strategy: {e}")
            return defaults

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

    async def update_setting(self, section: str, key: str, value: Any):
        if section not in self._data:
            self._data[section] = {}
        
        current_val = self._data[section].get(key)
        if current_val is not None:
            if isinstance(current_val, bool):
                value = str(value).lower() in ('true', '1', 'yes', 'on')
            elif isinstance(current_val, int):
                value = int(value)
            elif isinstance(current_val, float):
                value = float(value)
        
        self._data[section][key] = value
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
