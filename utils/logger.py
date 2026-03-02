import sys
from loguru import logger
import re

def mask_sensitive_data(message: str) -> str:
    """Masks potentially sensitive patterns like tokens or keys."""
    # Pattern for typical bot tokens 123456:ABC-DEF...
    token_pattern = r"\d{9,10}:[A-Za-z0-9_-]{35}"
    return re.sub(token_pattern, "[MASKED_TOKEN]", message)

def setup_logger(level: str = "INFO"):
    logger.remove()
    
    # Secure Console Handler (No sensitive data)
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True,
        filter=lambda record: mask_sensitive_data(record["message"])
    )
    
    # Secure File Handler (Rotation enabled, masked)
    logger.add(
        "logs/app.log",
        rotation="50 MB",
        retention="7 days",
        level="DEBUG",
        compression="zip",
        filter=lambda record: mask_sensitive_data(record["message"])
    )
    
    return logger

log = setup_logger()
