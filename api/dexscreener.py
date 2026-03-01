# ============================================================
# DEXSCREENER API CLIENT
# ============================================================

import asyncio
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import aiohttp
from aiohttp import ClientTimeout, ClientSession, ClientError
import json

from config.settings import get_config
from utils.logger import get_logger, log_execution_time
from utils.helpers import RateLimiter, retry_with_backoff, get_timestamp


logger = get_logger("dexscreener")


@dataclass
class TokenPair:
    """Represents a DEX token pair"""
    chain_id: str
    dex_id: str
    pair_address: str
    token_address: str
    token_name: str
    token_symbol: str
    token_logo: Optional[str] = None
    quote_token: str = "USDC"
    
    # Price data
    price_usd: float = 0.0
    price_change_5m: float = 0.0
    price_change_1h: float = 0.0
    price_change_24h: float = 0.0
    
    # Volume data
    volume_24h: float = 0.0
    volume_6h: float = 0.0
    volume_1h: float = 0.0
    
    # Liquidity data
    liquidity_usd: float = 0.0
    liquidity_base: float = 0.0
    liquidity_quote: float = 0.0
    
    # Transaction data
    txns_24h_buy: int = 0
    txns_24h_sell: int = 0
    txns_5m_buy: int = 0
    txns_5m_sell: int = 0
    
    # Market data
    market_cap: float = 0.0
    fdv: float = 0.0
    
    # Metadata
    pair_created_at: Optional[int] = None
    boost_active: bool = False
    boost_level: int = 0
    
    # Computed fields
    buy_ratio: float = field(default=0.0, init=False)
    sell_pressure: float = field(default=0.0, init=False)
    
    def __post_init__(self):
        self.buy_ratio = self._calculate_buy_ratio()
        self.sell_pressure = self._calculate_sell_pressure()
    
    def _calculate_buy_ratio(self) -> float:
        total = self.txns_24h_buy + self.txns_24h_sell
        if total == 0:
            return 0.5
        return self.txns_24h_buy / total
    
    def _calculate_sell_pressure(self) -> float:
        if self.txns_24h_buy + self.txns_24h_sell == 0:
            return 0.0
        return (self.txns_24h_sell - self.txns_24h_buy) / (self.txns_24h_buy + self.txns_24h_sell)
    
    @property
    def is_new_pair(self) -> bool:
        """Check if pair is new (less than 72 hours)"""
        if not self.pair_created_at:
            return False
        age_hours = (get_timestamp() - self.pair_created_at) / 3600
        return age_hours < 72
    
    @property
    def holder_estimate(self) -> int:
        """Estimate number of holders based on volume and transactions"""
        if self.txns_24h_buy == 0:
            return 0
        avg_trade_size = self.volume_24h / (self.txns_24h_buy + self.txns_24h_sell)
        if avg_trade_size == 0:
            return 0
        return int(self.volume_24h / avg_trade_size)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'chain_id': self.chain_id,
            'dex_id': self.dex_id,
            'pair_address': self.pair_address,
            'token_address': self.token_address,
            'token_name': self.token_name,
            'token_symbol': self.token_symbol,
            'price_usd': self.price_usd,
            'price_change_5m': self.price_change_5m,
            'price_change_24h': self.price_change_24h,
            'volume_24h': self.volume_24h,
            'liquidity_usd': self.liquidity_usd,
            'market_cap': self.market_cap,
            'txns_24h_buy': self.txns_24h_buy,
            'txns_24h_sell': self.txns_24h_sell,
            'buy_ratio': self.buy_ratio,
            'pair_created_at': self.pair_created_at,
            'is_new_pair': self.is_new_pair
        }


class DexScreenerClient:
    """Async client for DexScreener API"""
    
    def __init__(self):
        self.config = get_config()
        self.base_url = self.config.settings.DEXSCREENER_API_BASE
        self.session: Optional[ClientSession] = None
        self.rate_limiter = RateLimiter(max_calls=30, window_seconds=60)
        self._request_count = 0
        self._error_count = 0
        self._last_request_time = 0
        self._lock = asyncio.Lock()
    
    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30, connect=10)
            self.session = ClientSession(
                timeout=timeout,
                headers={
                    'Accept': 'application/json',
                    'User-Agent': 'DexIntelBot/1.0'
                }
            )
        return self.session
    
    async def close(self):
        """Close the HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Make rate-limited API request"""
        await self.rate_limiter.acquire()
        
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        async with self._lock:
            self._request_count += 1
            self._last_request_time = get_timestamp()
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 429:
                    logger.warning("Rate limit hit, backing off...")
                    await asyncio.sleep(5)
                    return None
                else:
                    logger.error(f"API error: {response.status}")
                    async with self._lock:
                        self._error_count += 1
                    return None
        except ClientError as e:
            logger.error(f"HTTP client error: {e}")
            async with self._lock:
                self._error_count += 1
            return None
        except asyncio.TimeoutError:
            logger.error("Request timeout")
            async with self._lock:
                self._error_count += 1
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            async with self._lock:
                self._error_count += 1
            return None
    
    def _parse_pair(self, pair_data: Dict) -> Optional[TokenPair]:
        """Parse API response into TokenPair object"""
        try:
            base_token = pair_data.get('baseToken', {})
            quote_token = pair_data.get('quoteToken', {})
            
            # Get price changes
            price_change = pair_data.get('priceChange', {})
            
            # Get volume
            volume = pair_data.get('volume', {})
            
            # Get transactions
            txns = pair_data.get('txns', {})
            txns_24h = txns.get('h24', {})
            txns_5m = txns.get('m5', {})
            
            # Get liquidity
            liquidity = pair_data.get('liquidity', {})
            
            return TokenPair(
                chain_id=pair_data.get('chainId', 'unknown'),
                dex_id=pair_data.get('dexId', 'unknown'),
                pair_address=pair_data.get('pairAddress', ''),
                token_address=base_token.get('address', ''),
                token_name=base_token.get('name', 'Unknown'),
                token_symbol=base_token.get('symbol', 'UNKNOWN'),
                token_logo=base_token.get('logoUrl'),
                quote_token=quote_token.get('symbol', 'USDC'),
                
                price_usd=float(pair_data.get('priceUsd', 0) or 0),
                price_change_5m=float(price_change.get('m5', 0) or 0),
                price_change_1h=float(price_change.get('h1', 0) or 0),
                price_change_24h=float(price_change.get('h24', 0) or 0),
                
                volume_24h=float(volume.get('h24', 0) or 0),
                volume_6h=float(volume.get('h6', 0) or 0),
                volume_1h=float(volume.get('h1', 0) or 0),
                
                liquidity_usd=float(liquidity.get('usd', 0) or 0),
                liquidity_base=float(liquidity.get('base', 0) or 0),
                liquidity_quote=float(liquidity.get('quote', 0) or 0),
                
                txns_24h_buy=int(txns_24h.get('buys', 0) or 0),
                txns_24h_sell=int(txns_24h.get('sells', 0) or 0),
                txns_5m_buy=int(txns_5m.get('buys', 0) or 0),
                txns_5m_sell=int(txns_5m.get('sells', 0) or 0),
                
                market_cap=float(pair_data.get('marketCap', 0) or 0),
                fdv=float(pair_data.get('fdv', 0) or 0),
                
                pair_created_at=pair_data.get('pairCreatedAt'),
                boost_active=pair_data.get('boostActive', False),
                boost_level=pair_data.get('boostLevel', 0)
            )
        except Exception as e:
            logger.error(f"Error parsing pair data: {e}")
            return None
    
    @log_execution_time("DEBUG")
    async def get_new_pairs(
        self,
        chain: Optional[str] = None,
        limit: int = 100
    ) -> List[TokenPair]:
        """Get new trading pairs"""
        endpoint = f"{self.config.settings.DEXSCREENER_PAIRS_ENDPOINT}"
        if chain:
            endpoint = f"{endpoint}/{chain}"
        
        data = await self._make_request(endpoint)
        if not data or 'pairs' not in data:
            return []
        
        pairs = []
        for pair_data in data['pairs'][:limit]:
            pair = self._parse_pair(pair_data)
            if pair:
                pairs.append(pair)
        
        logger.debug(f"Fetched {len(pairs)} pairs from DexScreener")
        return pairs
    
    @log_execution_time("DEBUG")
    async def search_pairs(
        self,
        query: str,
        limit: int = 50
    ) -> List[TokenPair]:
        """Search for trading pairs"""
        endpoint = "/dex/search"
        params = {'q': query}
        
        data = await self._make_request(endpoint, params)
        if not data or 'pairs' not in data:
            return []
        
        pairs = []
        for pair_data in data['pairs'][:limit]:
            pair = self._parse_pair(pair_data)
            if pair:
                pairs.append(pair)
        
        return pairs
    
    @log_execution_time("DEBUG")
    async def get_token_pairs(
        self,
        token_address: str
    ) -> List[TokenPair]:
        """Get all pairs for a specific token"""
        endpoint = f"{self.config.settings.DEXSCREENER_TOKENS_ENDPOINT}/{token_address}"
        
        data = await self._make_request(endpoint)
        if not data or 'pairs' not in data:
            return []
        
        pairs = []
        for pair_data in data['pairs']:
            pair = self._parse_pair(pair_data)
            if pair:
                pairs.append(pair)
        
        return pairs
    
    @log_execution_time("DEBUG")
    async def get_pair_details(
        self,
        chain: str,
        pair_address: str
    ) -> Optional[TokenPair]:
        """Get detailed information about a specific pair"""
        endpoint = f"/dex/pairs/{chain}/{pair_address}"
        
        data = await self._make_request(endpoint)
        if not data or 'pairs' not in data or not data['pairs']:
            return None
        
        return self._parse_pair(data['pairs'][0])
    
    async def get_top_boosted_tokens(
        self,
        limit: int = 50
    ) -> List[TokenPair]:
        """Get top boosted tokens"""
        # Get pairs and filter for boosted
        pairs = await self.get_new_pairs(limit=limit * 2)
        boosted = [p for p in pairs if p.boost_active]
        boosted.sort(key=lambda x: x.boost_level, reverse=True)
        return boosted[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        return {
            'total_requests': self._request_count,
            'total_errors': self._error_count,
            'error_rate': self._error_count / max(1, self._request_count),
            'last_request_time': self._last_request_time,
            'rate_limit_remaining': asyncio.run_coroutine_threadsafe(
                self.rate_limiter.get_remaining(), asyncio.get_event_loop()
            ).result() if self._request_count > 0 else self.rate_limiter.max_calls
        }


# ============================================================
# PAIR FILTER UTILITY
# ============================================================

class PairFilter:
    """Filter pairs based on strategy configuration"""
    
    def __init__(self):
        self.config = get_config()
        self.filters = self.config.strategy.filters
    
    def apply_stage1(self, pairs: List[TokenPair]) -> List[TokenPair]:
        """Apply stage 1 filters (basic criteria)"""
        filtered = []
        stage1 = self.filters.stage1
        
        for pair in pairs:
            # Check liquidity
            if pair.liquidity_usd < stage1.min_liquidity_usd:
                continue
            
            # Check volume
            if pair.volume_24h < stage1.min_volume_24h_usd:
                continue
            
            # Check market cap
            if pair.market_cap < stage1.min_market_cap_usd:
                continue
            
            # Check token age
            if pair.pair_created_at:
                age_hours = (get_timestamp() - pair.pair_created_at) / 3600
                if age_hours > stage1.max_token_age_hours:
                    continue
            
            # Check excluded chains
            if pair.chain_id in stage1.excluded_chains:
                continue
            
            filtered.append(pair)
        
        return filtered
    
    def apply_stage2(self, pairs: List[TokenPair]) -> List[TokenPair]:
        """Apply stage 2 filters (advanced criteria)"""
        filtered = []
        stage2 = self.filters.stage2
        
        for pair in pairs:
            # Check price change bounds
            if pair.price_change_5m < stage2.min_price_change_5m:
                continue
            if pair.price_change_5m > stage2.max_price_change_5m:
                continue
            
            # Check transaction count
            if (pair.txns_5m_buy + pair.txns_5m_sell) < stage2.min_transactions_5m:
                continue
            
            # Check buy ratio
            if pair.buy_ratio < stage2.min_buy_ratio:
                continue
            
            filtered.append(pair)
        
        return filtered
    
    def apply_all_filters(self, pairs: List[TokenPair]) -> List[TokenPair]:
        """Apply both filter stages"""
        stage1_filtered = self.apply_stage1(pairs)
        stage2_filtered = self.apply_stage2(stage1_filtered)
        return stage2_filtered


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_dexscreener_client: Optional[DexScreenerClient] = None


def get_dexscreener_client() -> DexScreenerClient:
    """Get or create DexScreener client singleton"""
    global _dexscreener_client
    if _dexscreener_client is None:
        _dexscreener_client = DexScreenerClient()
    return _dexscreener_client


async def close_dexscreener_client():
    """Close DexScreener client"""
    global _dexscreener_client
    if _dexscreener_client:
        await _dexscreener_client.close()
        _dexscreener_client = None
