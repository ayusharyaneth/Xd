# ============================================================
# UTILITY HELPERS
# ============================================================

import asyncio
import hashlib
import time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import deque
import json
import re


# ============================================================
# TIME UTILITIES
# ============================================================

def get_timestamp() -> int:
    """Get current timestamp in seconds"""
    return int(time.time())


def get_timestamp_ms() -> int:
    """Get current timestamp in milliseconds"""
    return int(time.time() * 1000)


def format_duration(seconds: int) -> str:
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


def parse_time_string(time_str: str) -> int:
    """Parse time string like '1h30m' to seconds"""
    pattern = r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?'
    match = re.match(pattern, time_str)
    if not match:
        return 0
    
    days, hours, minutes, seconds = match.groups()
    total_seconds = 0
    if days:
        total_seconds += int(days) * 86400
    if hours:
        total_seconds += int(hours) * 3600
    if minutes:
        total_seconds += int(minutes) * 60
    if seconds:
        total_seconds += int(seconds)
    
    return total_seconds


# ============================================================
# FORMATTING UTILITIES
# ============================================================

def format_currency(value: float, decimals: int = 2) -> str:
    """Format value as currency"""
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:.{decimals}f}B"
    elif value >= 1_000_000:
        return f"${value/1_000_000:.{decimals}f}M"
    elif value >= 1_000:
        return f"${value/1_000:.{decimals}f}K"
    else:
        return f"${value:.{decimals}f}"


def format_percentage(value: float, include_sign: bool = True) -> str:
    """Format value as percentage"""
    sign = "+" if include_sign and value > 0 else ""
    return f"{sign}{value:.2f}%"


def format_number(value: float, decimals: int = 2) -> str:
    """Format large numbers with K/M/B suffixes"""
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.{decimals}f}B"
    elif value >= 1_000_000:
        return f"{value/1_000_000:.{decimals}f}M"
    elif value >= 1_000:
        return f"{value/1_000:.{decimals}f}K"
    else:
        return f"{value:.{decimals}f}"


def shorten_address(address: str, prefix: int = 4, suffix: int = 4) -> str:
    """Shorten blockchain address"""
    if len(address) <= prefix + suffix:
        return address
    return f"{address[:prefix]}...{address[-suffix:]}"


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in escape_chars else c for c in text)


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to max length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


# ============================================================
# CRYPTO-SPECIFIC UTILITIES
# ============================================================

def calculate_price_impact(
    trade_size_usd: float,
    liquidity_usd: float,
    constant_product: bool = True
) -> float:
    """Calculate price impact of a trade"""
    if liquidity_usd <= 0:
        return 100.0
    
    if constant_product:
        # Constant product AMM formula
        return (trade_size_usd / (liquidity_usd + trade_size_usd)) * 100
    else:
        # Linear approximation
        return (trade_size_usd / liquidity_usd) * 100


def calculate_slippage(
    expected_price: float,
    executed_price: float
) -> float:
    """Calculate slippage percentage"""
    if expected_price <= 0:
        return 0.0
    return abs((executed_price - expected_price) / expected_price) * 100


def calculate_rug_pull_probability(
    liquidity_locked_percent: float,
    holder_concentration: float,
    contract_risk_score: float,
    developer_reputation: float
) -> float:
    """Calculate rug pull probability score"""
    # Weighted factors
    liquidity_factor = (100 - liquidity_locked_percent) * 0.3
    concentration_factor = holder_concentration * 0.25
    contract_factor = contract_risk_score * 0.25
    dev_factor = (100 - developer_reputation) * 0.2
    
    probability = liquidity_factor + concentration_factor + contract_factor + dev_factor
    return min(100, max(0, probability))


def detect_wash_trading(
    buy_count: int,
    sell_count: int,
    unique_buyers: int,
    unique_sellers: int,
    volume_24h: float
) -> float:
    """Detect wash trading score (0-1)"""
    if unique_buyers == 0 or unique_sellers == 0:
        return 0.5
    
    # Buyer/seller overlap indicator
    overlap_ratio = min(buy_count, sell_count) / max(buy_count, sell_count)
    
    # Unique participant ratio
    unique_ratio = (unique_buyers + unique_sellers) / (buy_count + sell_count)
    
    # Combined score
    wash_score = (overlap_ratio * 0.5) + ((1 - unique_ratio) * 0.5)
    return min(1.0, max(0.0, wash_score))


# ============================================================
# DATA STRUCTURES
# ============================================================

class SlidingWindow:
    """Thread-safe sliding window for metrics"""
    
    def __init__(self, window_size: int):
        self.window_size = window_size
        self._data: deque = deque(maxlen=window_size)
        self._lock = asyncio.Lock()
    
    async def add(self, value: float):
        """Add value to window"""
        async with self._lock:
            self._data.append(value)
    
    async def get_all(self) -> List[float]:
        """Get all values in window"""
        async with self._lock:
            return list(self._data)
    
    async def get_average(self) -> float:
        """Get average of window"""
        async with self._lock:
            if not self._data:
                return 0.0
            return sum(self._data) / len(self._data)
    
    async def get_max(self) -> float:
        """Get maximum in window"""
        async with self._lock:
            if not self._data:
                return 0.0
            return max(self._data)
    
    async def get_min(self) -> float:
        """Get minimum in window"""
        async with self._lock:
            if not self._data:
                return 0.0
            return min(self._data)
    
    async def clear(self):
        """Clear window"""
        async with self._lock:
            self._data.clear()


class TimedCache:
    """Cache with TTL expiration"""
    
    def __init__(self, default_ttl: int = 300):
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        async with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            if get_timestamp() > entry['expires']:
                del self._cache[key]
                return None
            
            return entry['value']
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache with TTL"""
        async with self._lock:
            ttl = ttl or self.default_ttl
            self._cache[key] = {
                'value': value,
                'expires': get_timestamp() + ttl
            }
    
    async def delete(self, key: str):
        """Delete key from cache"""
        async with self._lock:
            self._cache.pop(key, None)
    
    async def clear(self):
        """Clear all cache"""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup_expired(self):
        """Remove expired entries"""
        async with self._lock:
            current_time = get_timestamp()
            expired_keys = [
                k for k, v in self._cache.items()
                if current_time > v['expires']
            ]
            for key in expired_keys:
                del self._cache[key]


class RateLimiter:
    """Rate limiter for API calls"""
    
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls: deque = deque()
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire rate limit slot"""
        async with self._lock:
            current_time = get_timestamp()
            
            # Remove old calls outside window
            while self._calls and self._calls[0] < current_time - self.window_seconds:
                self._calls.popleft()
            
            # Check if we can make a call
            if len(self._calls) >= self.max_calls:
                sleep_time = self._calls[0] - (current_time - self.window_seconds) + 1
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            
            self._calls.append(current_time)
    
    async def get_remaining(self) -> int:
        """Get remaining calls in window"""
        async with self._lock:
            current_time = get_timestamp()
            while self._calls and self._calls[0] < current_time - self.window_seconds:
                self._calls.popleft()
            return max(0, self.max_calls - len(self._calls))


# ============================================================
# COOLDOWN MANAGER
# ============================================================

class CooldownManager:
    """Manage cooldowns for tokens and alerts"""
    
    def __init__(self):
        self._cooldowns: Dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    async def is_on_cooldown(self, key: str) -> bool:
        """Check if key is on cooldown"""
        async with self._lock:
            if key not in self._cooldowns:
                return False
            return get_timestamp() < self._cooldowns[key]
    
    async def set_cooldown(self, key: str, duration_seconds: int):
        """Set cooldown for key"""
        async with self._lock:
            self._cooldowns[key] = get_timestamp() + duration_seconds
    
    async def clear_cooldown(self, key: str):
        """Clear cooldown for key"""
        async with self._lock:
            self._cooldowns.pop(key, None)
    
    async def get_remaining(self, key: str) -> int:
        """Get remaining cooldown seconds"""
        async with self._lock:
            if key not in self._cooldowns:
                return 0
            remaining = self._cooldowns[key] - get_timestamp()
            return max(0, remaining)
    
    async def cleanup_expired(self):
        """Remove expired cooldowns"""
        async with self._lock:
            current_time = get_timestamp()
            expired = [k for k, v in self._cooldowns.items() if current_time > v]
            for key in expired:
                del self._cooldowns[key]


# ============================================================
# HASHING & IDENTIFIERS
# ============================================================

def generate_id(*args) -> str:
    """Generate unique ID from arguments"""
    content = ''.join(str(arg) for arg in args)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def hash_token_address(address: str) -> str:
    """Hash token address for internal tracking"""
    return hashlib.sha256(address.lower().encode()).hexdigest()


# ============================================================
# VALIDATION UTILITIES
# ============================================================

def is_valid_solana_address(address: str) -> bool:
    """Validate Solana address format"""
    if not address or len(address) < 32 or len(address) > 44:
        return False
    try:
        import base58
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except:
        return False


def is_valid_ethereum_address(address: str) -> bool:
    """Validate Ethereum address format"""
    if not address or not address.startswith('0x'):
        return False
    if len(address) != 42:
        return False
    try:
        int(address[2:], 16)
        return True
    except ValueError:
        return False


# ============================================================
# ASYNC UTILITIES
# ============================================================

async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
):
    """Retry function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            if attempt == max_retries - 1:
                raise
            
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger = get_logger()
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)


async def run_with_timeout(coro, timeout: float, default=None):
    """Run coroutine with timeout"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


from utils.logger import get_logger


# ============================================================
# JSON UTILITIES
# ============================================================

class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime and other types"""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)


def safe_json_dumps(obj: Any, indent: Optional[int] = None) -> str:
    """Safely serialize to JSON"""
    try:
        return json.dumps(obj, cls=JSONEncoder, indent=indent)
    except (TypeError, ValueError) as e:
        return json.dumps({"error": f"Serialization failed: {str(e)}"})


def safe_json_loads(text: str, default: Any = None) -> Any:
    """Safely deserialize from JSON"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default
