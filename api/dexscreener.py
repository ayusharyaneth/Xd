import aiohttp
import asyncio
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import settings
from utils.logger import log

class DexScreenerAPI:
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest/dex"
        self.ua = UserAgent()
        self.session = None

    async def start(self):
        # Optimized TCPConnector for high concurrency
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
        # NOTE: DexScreener requires specific pair addresses or search queries usually.
        # The endpoint /tokens/{address} is for specific tokens.
        # To monitor "new" tokens, we search by chain ID if supported or use /search
        # For this implementation, we use a search query simulation for 'new' or specific known pairs logic.
        # Since 'latest' isn't a simple public endpoint, we use the search endpoint sorted by age if available,
        # or we assume we are given a list of pairs.
        
        # PRODUCTION STRATEGY: 
        # Since we can't scrape 'New Pairs' directly without paid API or specific scraping logic,
        # We will use the search endpoint for the specific chain to get active pairs.
        url = f"{self.base_url}/search/?q={chain}" 
        
        if not self.session: await self.start()
        
        async with self.session.get(url, headers=self._get_headers(), timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('pairs', [])
            elif resp.status == 429:
                log.warning("Rate limited by DexScreener")
                raise Exception("RateLimit")
            else:
                log.error(f"API Error: {resp.status}")
                return []

    async def get_pairs_bulk(self, addresses: list):
        if not addresses: return []
        # Chunking to avoid URL length limits (30 addresses max per call)
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
                log.error(f"Failed to fetch chunk: {e}")
                
        return results
