import sys
from loguru import logger

def setup_logger(log_level: str = "INFO"):
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True
    )
    logger.add("logs/system.log", rotation="50 MB", retention="10 days", level="DEBUG")
    return logger
