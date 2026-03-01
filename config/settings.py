import os
import sys
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, ValidationError
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load .env with explicit path
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    logger.info(f"Loaded .env from {env_path}")
else:
    load_dotenv()  # Try default locations
    logger.warning(f".env not found at {env_path}, trying system env")

def load_yaml_config():
    """Load strategy.yaml with better path resolution"""
    # Try multiple path strategies
    possible_paths = [
        Path("strategy.yaml"),  # Current directory
        Path(__file__).parent.parent / "strategy.yaml",  # Relative to this file
        Path.cwd() / "strategy.yaml",  # Working directory
    ]
    
    for path in possible_paths:
        try:
            if path.exists():
                with open(path, "r") as f:
                    config = yaml.safe_load(f) or {}
                    logger.info(f"Loaded strategy config from {path}")
                    return config
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            continue
    
    logger.warning("No strategy.yaml found, using defaults")
    return {}

yaml_config = load_yaml_config()

class Settings(BaseSettings):
    # Required fields with validation error messages
    SIGNAL_BOT_TOKEN: str = Field(
        default=None,
        description="Telegram token for signal bot (@BotFather)"
    )
    ALERT_BOT_TOKEN: str = Field(
        default=None, 
        description="Telegram token for alert bot (@BotFather)"
    )
    SIGNAL_CHAT_ID: str = Field(
        default=None,
        description="Chat ID for signal messages"
    )
    ALERT_CHAT_ID: str = Field(
        default=None,
        description="Chat ID for alert messages"
    )
    
    # Optional fields with sensible defaults
    DEXSCREENER_API_BASE: str = Field(default="https://api.dexscreener.com/latest/dex")
    RPC_BASE_URL: str = Field(default="http://localhost:8545")
    POLL_INTERVAL: int = Field(default=60, ge=5, le=3600)
    
    # Strategy configs with safe defaults
    MAX_FDV: float = Field(default=yaml_config.get('risk', {}).get('max_fdv', 10000000))
    MIN_LIQUIDITY: float = Field(default=yaml_config.get('risk', {}).get('min_liquidity', 5000))
    MIN_WHALE_TRADE: float = Field(default=yaml_config.get('whale', {}).get('min_trade_usd', 10000))
    MAX_ERROR_RATE: float = Field(default=yaml_config.get('self_defense', {}).get('max_error_rate', 0.2))
    MAX_LATENCY_MS: float = Field(default=yaml_config.get('self_defense', {}).get('max_latency_ms', 2000))
    MAX_MEMORY_PERCENT: float = Field(default=yaml_config.get('self_defense', {}).get('max_memory_percent', 85.0))
    ALERT_COOLDOWN_SECONDS: int = Field(default=yaml_config.get('alert', {}).get('alert_cooldown_seconds', 600))
    WATCH_EXPIRY_SECONDS: int = Field(default=yaml_config.get('watch', {}).get('watch_expiry_seconds', 86400))

    class Config:
        env_file = ".env"
        extra = "ignore"
        case_sensitive = True

# Initialize with validation
try:
    settings = Settings()
    
    # Post-init validation
    missing = []
    if not settings.SIGNAL_BOT_TOKEN:
        missing.append("SIGNAL_BOT_TOKEN")
    if not settings.ALERT_BOT_TOKEN:
        missing.append("ALERT_BOT_TOKEN")
    if not settings.SIGNAL_CHAT_ID:
        missing.append("SIGNAL_CHAT_ID")
    if not settings.ALERT_CHAT_ID:
        missing.append("ALERT_CHAT_ID")
    
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Please ensure these are set in your .env file")
        # Don't exit - let the bot fail gracefully when trying to send first message
        # So user can see specific error about which bot failed
        
    logger.info("Settings loaded successfully")
    
except ValidationError as e:
    logger.error(f"Configuration validation error: {e}")
    raise SystemExit(1)
except Exception as e:
    logger.error(f"Unexpected error loading settings: {e}")
    raise
