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
    POLL_INTERVAL: int = 60
    TARGET_CHAIN: str = Field(default="solana", description="Default blockchain to monitor")
    FETCH_LIMIT: int = Field(default=300, description="Max tokens to fetch per cycle")

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def admin_list(self) -> List[int]:
        if not self.ADMIN_IDS: return []
        try:
            return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]
        except ValueError: return []

    def get_admins(self) -> List[int]:
        return self.admin_list

    @field_validator("LOG_CHANNEL_ID", mode="before")
    @classmethod
    def validate_log_channel(cls, v):
        if v == "" or v is None: return None
        return int(v)

class StrategyConfig:
    def __init__(self):
        self.filepath = "strategy.yaml"
        self._lock = asyncio.Lock()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        defaults = {
            "filters": {
                "min_liquidity_usd": 1000,
                "max_age_hours": 24,
                "min_volume_h1": 500,
                "max_fdv": 0,
                "min_fdv": 0
            }, 
            "weights": {
                "volume_authenticity": 1.5,
                "liquidity_score": 1.0,
                "whale_presence": 2.0,
                "dev_reputation": 1.0
            }, 
            "thresholds": {
                "risk_alert_level": 70,
                "strict_filtering": True,
                "take_profit_percent": 100,
                "stop_loss_percent": -25
            },
            "system": {
                "fetch_limit": 300 # Default matches typical API max per call
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
        async with self._lock:
            self._data = self._load()

    async def save(self):
        async with self._lock:
            try:
                with open(self.filepath, "w") as f:
                    yaml.dump(self._data, f, default_flow_style=False)
            except Exception as e:
                print(f"Error saving strategy: {e}")

    async def update_setting(self, section: str, key: str, value: Any):
        if section not in self._data: self._data[section] = {}
        
        current_val = self._data[section].get(key)
        if current_val is not None:
            if isinstance(current_val, bool):
                value = str(value).lower() in ('true', '1', 'yes', 'on')
            elif isinstance(current_val, int):
                try: value = int(value)
                except: return
            elif isinstance(current_val, float):
                try: value = float(value)
                except: return
        
        self._data[section][key] = value
        await self.save()

    @property
    def filters(self): return self._data.get('filters', {})
    @property
    def weights(self): return self._data.get('weights', {})
    @property
    def thresholds(self): return self._data.get('thresholds', {})
    @property
    def system(self): return self._data.get('system', {})

    def get_parameter_description(self, section, key):
        descriptions = {
            "filters": {
                "min_liquidity_usd": "Minimum Pool Liquidity (USD).",
                "max_age_hours": "Maximum Token Age (Hours).",
                "min_volume_h1": "Minimum 1-Hour Volume (USD).",
                "max_fdv": "Maximum FDV. 0 = Disabled.",
                "min_fdv": "Minimum FDV. 0 = Disabled."
            },
            "weights": {
                "volume_authenticity": "Volume Quality Weight.",
                "liquidity_score": "Liquidity Weight.",
                "whale_presence": "Whale Detection Weight.",
                "dev_reputation": "Developer Reputation Weight."
            },
            "thresholds": {
                "strict_filtering": "Strict Mode (True/False).",
                "risk_alert_level": "Risk Score Threshold (0-100).",
                "take_profit_percent": "TP %.",
                "stop_loss_percent": "SL %."
            },
            "system": {
                "fetch_limit": "Max tokens fetched per cycle from API (Max 600 rec)."
            }
        }
        return descriptions.get(section, {}).get(key, "Internal parameter.")

# Singletons
settings = Settings()
strategy = StrategyConfig()
