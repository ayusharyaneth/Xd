import aiohttp
import asyncio
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import settings
from utils.logger import log

class DexScreenerAPI:
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest/dex"
        # Using token-profiles endpoint to get the latest tokens across all chains
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
        Fetches the latest token profiles for a specific chain.
        This endpoint returns a list of recently updated/added tokens.
        """
        url = self.token_profiles_url
        log.debug(f"Fetching token profiles from: {url}")
        
        if not self.session: await self.start()

        try:
            async with self.session.get(url, headers=self._get_headers(), timeout=10) as resp:
                if resp.status == 200:
                    profiles = await resp.json()
                    
                    # Log raw fetch count for debugging
                    log.debug(f"Raw profiles fetched: {len(profiles)}")
                    
                    # Filter by chain immediately to save processing downstream
                    target_tokens = [
                        p['tokenAddress'] for p in profiles 
                        if p.get('chainId') == chain.lower()
                    ]
                    
                    log.debug(f"Tokens matching chain '{chain}': {len(target_tokens)}")
                    
                    if not target_tokens:
                        return []
                    
                    # DexScreener bulk endpoint supports up to 30 addresses per request.
                    # We will fetch up to 60 tokens (2 batches) to increase coverage.
                    # You can increase this limit if needed, but respect rate limits.
                    limit = 60 
                    limited_tokens = target_tokens[:limit]
                    
                    log.debug(f"Fetching pair data for {len(limited_tokens)} tokens...")
                    return await self.get_pairs_bulk(limited_tokens)
                    
                else:
                    log.error(f"Token profiles fetch failed. Status: {resp.status}")
                    return []
                    
        except Exception as e:
            log.warning(f"Token profiles fetch exception: {e}")
            # Fallback to search is removed to enforce 'New' token logic via profiles
            return []

    async def get_pairs_bulk(self, addresses: list):
        if not addresses: return []
        
        # DexScreener allows max 30 addresses per bulk request
        chunk_size = 30
        chunks = [addresses[i:i + chunk_size] for i in range(0, len(addresses), chunk_size)]
        results = []
        
        if not self.session: await self.start()

        for chunk in chunks:
            url = f"{self.base_url}/tokens/{','.join(chunk)}"
            try:
                async with self.session.get(url, headers=self._get_headers(), timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # The API returns 'pairs' which is a list of pair objects.
                        # Multiple pairs can exist for one token (different DEXs).
                        # We aggregate all returned pairs.
                        chunk_pairs = data.get('pairs', [])
                        
                        # Optional: If you only want the most liquid pair per token, logic should go here.
                        # For now, we return all to let the filter engine decide.
                        results.extend(chunk_pairs)
                    else:
                        log.warning(f"Bulk fetch failed for chunk. Status: {resp.status}")
                        
            except Exception as e:
                log.error(f"Bulk fetch exception: {e}")
                
        log.debug(f"Total pair data fetched: {len(results)}")
        return results
