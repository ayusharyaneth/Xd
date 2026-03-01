from datetime import datetime
from zoneinfo import ZoneInfo

# Centralized Timezone Configuration
TIMEZONE = ZoneInfo("Asia/Kolkata")

def get_current_time_str(fmt: str = "%H:%M:%S") -> str:
    """Returns current time string in IST."""
    return datetime.now(TIMEZONE).strftime(fmt)

def get_current_datetime_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Returns current datetime string in IST."""
    return datetime.now(TIMEZONE).strftime(fmt)

def get_time_obj():
    """Returns datetime object in IST."""
    return datetime.now(TIMEZONE)

def format_number(num):
    if not num: return "0"
    if num >= 1_000_000:
        return f"${num/1_000_000:.2f}M"
    if num >= 1_000:
        return f"${num/1_000:.2f}K"
    return f"${num:.2f}"
