import os
import yaml
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()

def load_yaml_config():
    try:
        with open("strategy.yaml", "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

yaml_config = load_yaml_config()

class Settings(BaseSettings):
    SIGNAL_BOT_TOKEN: str = Field(...)
    ALERT_BOT_TOKEN: str = Field(...)
    SIGNAL_CHAT_ID: str = Field(...)
    ALERT_CHAT_ID: str = Field(...)
    DEXSCREENER_API_BASE: str = Field("https://api.dexscreener.com/latest/dex")
    RPC_BASE_URL: str = Field("http://localhost:8545")
    POLL_INTERVAL: int = Field(60)
    
    # Strategy configs injected via YAML or overridden by ENV
    MAX_FDV: float = Field(yaml_config.get('risk', {}).get('max_fdv', 10000000))
    MIN_LIQUIDITY: float = Field(yaml_config.get('risk', {}).get('min_liquidity', 5000))
    MIN_WHALE_TRADE: float = Field(yaml_config.get('whale', {}).get('min_trade_usd', 10000))
    MAX_ERROR_RATE: float = Field(yaml_config.get('self_defense', {}).get('max_error_rate', 0.2))
    MAX_LATENCY_MS: float = Field(yaml_config.get('self_defense', {}).get('max_latency_ms', 2000))
    MAX_MEMORY_PERCENT: float = Field(yaml_config.get('self_defense', {}).get('max_memory_percent', 85.0))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
