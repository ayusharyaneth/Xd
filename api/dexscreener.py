import aiohttp
from utils.logger import logger
from config.settings import settings
from system.metrics import metrics

class DexScreenerAPI:
    def __init__(self):
        self.base_url = settings.DEXSCREENER_API_BASE
        self._session = None
        self._session_lock = asyncio.Lock()

    async def get_session(self):
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()
            return self._session

    async def fetch_latest_pairs(self, limit: int = 100):
        """Fetch latest tokens from DexScreener with proper endpoint"""
        session = await self.get_session()
        start_time = metrics.start_timer()
        
        try:
            # CORRECT ENDPOINT: latest boosted tokens (most active)
            url = f"{self.base_url}/token-profiles/latest/v1"
            # Alternative: "/token-boosts/latest/v1" for boosted tokens
            # Alternative: "/token-boosts/top/v1" for top boosted
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                data = await response.json()
                metrics.record_api_call("dexscreener_success", metrics.stop_timer(start_time))
                
                pairs = data.get("pairs", [])
                if not pairs:
                    # Try alternative endpoint if empty
                    logger.warning("No pairs from primary endpoint, trying search...")
                    pairs = await self._fallback_search(session)
                
                logger.info(f"Fetched {len(pairs)} pairs from DexScreener")
                return pairs

        except aiohttp.ClientResponseError as e:
            metrics.record_api_call("dexscreener_error", metrics.stop_timer(start_time))
            logger.error(f"DexScreener API HTTP error: {e.status} - {e.message}")
            return []
        except asyncio.TimeoutError:
            metrics.record_api_call("dexscreener_timeout", metrics.stop_timer(start_time))
            logger.error("DexScreener API timeout")
            return []
        except Exception as e:
            metrics.record_api_call("dexscreener_error", metrics.stop_timer(start_time))
            logger.error(f"DexScreener API error: {e}")
            return []
    
    async def _fallback_search(self, session, query: str = "solana"):
        """Fallback search if primary endpoint fails"""
        try:
            url = f"{self.base_url}/search?q={query}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("pairs", [])[:20]  # Limit fallback results
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
        return []

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
            logger.info("DexScreener API session closed")

import asyncio  # Added for lock
dex_api = DexScreenerAPI()
