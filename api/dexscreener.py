import aiohttp
import asyncio
from loguru import logger
from config.settings import settings

class DexScreenerClient:
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest/dex"
        self.session = None

    async def start(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def get_token_pairs(self, chain: str, token_address: str):
        url = f"{self.base_url}/tokens/{token_address}"
        return await self._fetch(url)

    async def get_latest_pairs(self):
        # Note: DexScreener doesn't have a pure "newest" endpoint public in all docs,
        # using a specific chain endpoint or search is common. 
        # For this implementation, we simulate fetching by contract or use a known search logic.
        # Assuming we are monitoring specific addresses or a feed in a real scenario.
        # Here we implement the generic fetch structure.
        pass

    async def get_pairs_by_chain(self, chain_id: str):
        # Implementation for specific chain polling
        pass
    
    async def get_multiple_tokens(self, addresses: list):
        if not addresses: return []
        results = []
        # Dexscreener allows comma separated, but limited length. Batching needed.
        chunk_size = 30
        for i in range(0, len(addresses), chunk_size):
            chunk = addresses[i:i + chunk_size]
            url = f"{self.base_url}/tokens/{','.join(chunk)}"
            data = await self._fetch(url)
            if data and 'pairs' in data:
                results.extend(data['pairs'])
        return results

    async def _fetch(self, url):
        if not self.session: await self.start()
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API Error {response.status}: {url}")
                    return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None
