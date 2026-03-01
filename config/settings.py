import os
import logging
from dotenv import load_dotenv

# Load environment variables from the .env file in the root directory
load_dotenv()

# ---------------------------------------------------------
# Telegram Bot Configurations
# ---------------------------------------------------------
SIGNAL_BOT_TOKEN = os.getenv("SIGNAL_BOT_TOKEN")
ALERT_BOT_TOKEN = os.getenv("ALERT_BOT_TOKEN")

# Chat ID where the Alert Bot will broadcast critical warnings
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# ---------------------------------------------------------
# System & Watch Configurations
# ---------------------------------------------------------
# How often to poll DexScreener (in seconds)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15")) 

# Logging Level (INFO, DEBUG, WARNING, ERROR)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ---------------------------------------------------------
# DexScreener API Configurations
# ---------------------------------------------------------
DEXSCREENER_BASE_URL = "https://api.dexscreener.com/latest/dex"
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))

# ---------------------------------------------------------
# Intelligence System Thresholds
# ---------------------------------------------------------
# Minimum transaction size in USD to trigger a Whale Alert
WHALE_BUY_THRESHOLD_USD = float(os.getenv("WHALE_BUY_THRESHOLD_USD", "50000.0"))

# Probability threshold (0-100) to flag a newly listed token as a potential rug pull
RUG_RISK_THRESHOLD = float(os.getenv("RUG_RISK_THRESHOLD", "85.0"))

# ---------------------------------------------------------
# Startup Validation
# ---------------------------------------------------------
def validate_settings():
    """Ensure all critical environment variables are loaded before startup."""
    missing_keys = []
    
    if not SIGNAL_BOT_TOKEN:
        missing_keys.append("SIGNAL_BOT_TOKEN")
    if not ALERT_BOT_TOKEN:
        missing_keys.append("ALERT_BOT_TOKEN")
        
    if missing_keys:
        error_msg = f"CRITICAL Startup Error: Missing environment variables: {', '.join(missing_keys)}"
        logging.error(error_msg)
        raise ValueError(error_msg)

# Run validation immediately upon import
validate_settings()
