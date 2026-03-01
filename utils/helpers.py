from datetime import datetime
from zoneinfo import ZoneInfo

# Define Timezone globally
IST = ZoneInfo("Asia/Kolkata")

def get_ist_datetime() -> datetime:
    """Returns current timezone-aware datetime object in IST."""
    return datetime.now(IST)

def get_ist_time_str(fmt: str = "%H:%M:%S IST") -> str:
    """Returns current time in IST formatted as string. Default: HH:MM:SS IST"""
    return get_ist_datetime().strftime(fmt)

def get_current_datetime_str(fmt: str = "%Y-%m-%d %H:%M:%S IST") -> str:
    """
    Returns current full datetime in IST formatted as string.
    Default: YYYY-MM-DD HH:MM:SS IST
    """
    return get_ist_datetime().strftime(fmt)

def format_number(num):
    if not num: return "0"
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    if num >= 1_000:
        return f"{num/1_000:.2f}K"
    return f"{num:.2f}"
