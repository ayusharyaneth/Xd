import aiohttp
import asyncio
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import settings, strategy
from utils.logger import log
import time

class DexScreenerAPI:
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest/dex"
        self.token_profiles_url = "https://api.dexscreener.com/token-profiles/latest/v1"
        self.ua = UserAgent()
        self.session = None
        self._rate_limit_lock = asyncio.Lock()
        self.last_request_time = 0
        self.request_interval = 0.2

    async def start(self):
        if self.session and not self.session.closed: return
        connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(connector=connector)

    async def close(self):
        if self.session: await self.session.close()

    def _get_headers(self):
        return {
            "User-Agent": self.ua.random,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate"
        }

    async def _throttle(self):
        async with self._rate_limit_lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.request_interval:
                await asyncio.sleep(self.request_interval - elapsed)
            self.last_request_time = time.time()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def get_pairs_by_chain(self, chain: str):
        """
        Fetches profiles and then pair data.
        Respects strategy.system.fetch_limit.
        """
        if not self.session: await self.start()
        
        limit = strategy.system.get('fetch_limit', settings.FETCH_LIMIT)
        # Cap limit to prevent abuse/timeout
        limit = min(limit, 600) 
        
        try:
            await self._throttle()
            async with self.session.get(self.token_profiles_url, headers=self._get_headers(), timeout=15) as resp:
                if resp.status == 200:
                    profiles = await resp.json()
                    
                    target_tokens = [
                        p['tokenAddress'] for p in profiles 
                        if p.get('chainId') == chain.lower()
                    ]
                    
                    if not target_tokens:
                        return []
                    
                    # Apply configurable limit
                    target_tokens = target_tokens[:limit]
                    
                    log.debug(f"Fetch target: {len(target_tokens)} tokens (Limit: {limit})")
                    return await self.get_pairs_bulk(target_tokens)
                    
                else:
                    log.warning(f"Profiles fetch failed: {resp.status}")
                    return []
                    
        except Exception as e:
            log.error(f"API Profile Fetch Error: {e}")
            return []

    async def get_pairs_bulk(self, addresses: list):
        if not addresses: return []
        if not self.session: await self.start()
        
        # DexScreener bulk endpoint supports max 30 per call
        chunk_size = 30
        chunks = [addresses[i:i + chunk_size] for i in range(0, len(addresses), chunk_size)]
        
        tasks = []
        for chunk in chunks:
            url = f"{self.base_url}/tokens/{','.join(chunk)}"
            tasks.append(self._fetch_chunk(url))
            
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        for res in chunk_results:
            if isinstance(res, list):
                results.extend(res)
            elif isinstance(res, Exception):
                log.error(f"Chunk fetch failed: {res}")

        log.debug(f"API Response: {len(results)} pairs retrieved")
        return results

    async def _fetch_chunk(self, url):
        try:
            await self._throttle()
            async with self.session.get(url, headers=self._get_headers(), timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # DexScreener returns all pairs; usually we want the most liquid one.
                    # We return all for the filter engine to decide.
                    return data.get('pairs', [])
                else:
                    return []
        except Exception as e:
            log.error(f"Fetch Chunk Error: {e}")
            return []
