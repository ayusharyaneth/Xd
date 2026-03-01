import aiohttp
import asyncio
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import log

class DexScreenerAPI:
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest/dex"
        self.ua = UserAgent()
        self.session = None

    async def start(self):
        connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(connector=connector)

    async def close(self):
        if self.session:
            await self.session.close()

    def _get_headers(self):
        return {
            "User-Agent": self.ua.random,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate"
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_pairs_by_chain(self, chain: str):
        """
        Fetches pairs. 
        Note: The 'search' endpoint returns relevant/trending pairs.
        It does NOT strictly return 'newest' pairs. 
        """
        # We search specifically for the chain name to get a list of active pairs
        url = f"{self.base_url}/search/?q={chain}" 
        
        if not self.session: await self.start()
        
        try:
            async with self.session.get(url, headers=self._get_headers(), timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get('pairs', [])
                    log.debug(f"Fetched {len(pairs)} pairs from API for chain: {chain}")
                    return pairs
                elif resp.status == 429:
                    log.warning("Rate limited by DexScreener (429)")
                    raise Exception("RateLimit")
                else:
                    log.error(f"API Error: {resp.status} - {url}")
                    return []
        except Exception as e:
            log.error(f"Fetch failed: {e}")
            return []

    async def get_pairs_bulk(self, addresses: list):
        if not addresses: return []
        chunks = [addresses[i:i + 30] for i in range(0, len(addresses), 30)]
        results = []
        
        if not self.session: await self.start()

        for chunk in chunks:
            url = f"{self.base_url}/tokens/{','.join(chunk)}"
            try:
                async with self.session.get(url, headers=self._get_headers(), timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results.extend(data.get('pairs', []))
            except Exception as e:
                log.error(f"Bulk fetch failed: {e}")
                
        return results
