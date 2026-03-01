import datetime

def format_number(num):
    if not num: return "0"
    if num >= 1_000_000:
        return f"${num/1_000_000:.2f}M"
    if num >= 1_000:
        return f"${num/1_000:.2f}K"
    return f"${num:.2f}"

def time_ago(timestamp_ms):
    if not timestamp_ms: return "Unknown"
    dt = datetime.datetime.fromtimestamp(timestamp_ms / 1000)
    now = datetime.datetime.now()
    diff = now - dt
    minutes = int(diff.total_seconds() / 60)
    return f"{minutes}m ago"
