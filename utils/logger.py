import sys
from loguru import logger

# Expose the logger object immediately.
# This ensures that other modules (like config/settings.py) can import 'log' 
# without triggering circular dependency errors or NameErrors.
log = logger

def setup_logger(level: str = "INFO"):
    """
    Configures the logger handlers.
    This must be called explicitly from main.py after settings are loaded.
    """
    # Remove default handler
    logger.remove()
    
    # Console Handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True
    )
    
    # File Handler (Rotation enabled)
    logger.add(
        "logs/app.log",
        rotation="100 MB",
        retention="7 days",
        level="DEBUG",
        compression="zip"
    )
