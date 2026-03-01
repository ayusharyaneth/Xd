import time

def current_milli_time():
    return round(time.time() * 1000)

def format_usd(value: float) -> str:
    return f"{value:,.2f} USD"
