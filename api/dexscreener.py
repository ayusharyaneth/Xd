import aiohttp
import asyncio
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import settings
from utils.logger import log

class DexScreenerAPI:
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest/dex"
        self.token_profiles_url = "https://api.dexscreener.com/token-profiles/latest/v1"
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
        Fetches the latest token profiles or pairs for a specific chain.
        DexScreener recently introduced token-profiles endpoint which is better for 'new' tokens.
        If that fails or returns empty, we fall back to search or specific chain logic.
        """
        # Strategy 1: Attempt to get latest token profiles (Newest additions)
        # Note: This endpoint provides a list of recently updated/added tokens.
        try:
            url = self.token_profiles_url
            if not self.session: await self.start()

            async with self.session.get(url, headers=self._get_headers(), timeout=10) as resp:
                if resp.status == 200:
                    profiles = await resp.json()
                    # Filter by chain immediately to save processing downstream
                    # Profiles usually have 'chainId' and 'tokenAddress'
                    # We need to fetch pair data for these tokens to get liquidity/price
                    target_tokens = [
                        p['tokenAddress'] for p in profiles 
                        if p.get('chainId') == chain.lower()
                    ]
                    
                    if target_tokens:
                        # Limit to batch size (30) to avoid URL length issues
                        return await self.get_pairs_bulk(target_tokens[:30])
        except Exception as e:
            log.warning(f"Token profiles fetch failed: {e}. Falling back to search.")

        # Strategy 2: Search fallback (Trending/Relevant)
        # This is less ideal for 'new' but robust as a backup
        url = f"{self.base_url}/search/?q={chain}" 
        
        try:
            async with self.session.get(url, headers=self._get_headers(), timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('pairs', [])
                elif resp.status == 429:
                    log.warning("Rate limited by DexScreener (429)")
                    raise Exception("RateLimit")
                else:
                    log.error(f"API Error: {resp.status} - {url}")
                    return []
        except Exception as e:
            log.error(f"Search fetch failed: {e}")
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
                        # DexScreener returns 'pairs' list, we want the most liquid pair for each token usually
                        # But here we just return all pairs found
                        chunk_pairs = data.get('pairs', [])
                        results.extend(chunk_pairs)
            except Exception as e:
                log.error(f"Bulk fetch failed for chunk: {e}")
                
        return results
