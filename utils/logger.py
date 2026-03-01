import sys
from loguru import logger

def setup_logger(level: str = "INFO"):
    logger.remove()
    # Console Handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level
    )
    # File Handler (Rotation enabled)
    logger.add(
        "logs/app.log",
        rotation="100 MB",
        retention="7 days",
        level="DEBUG",
        compression="zip"
    )
    return logger

log = setup_logger(settings.LOG_LEVEL)
