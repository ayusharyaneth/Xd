import aiohttp
from utils.logger import logger
from config.settings import settings
from system.metrics import metrics

class DexScreenerAPI:
    def __init__(self):
        self.base_url = settings.DEXSCREENER_API_BASE
        self.session = None

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def fetch_latest_pairs(self):
        session = await self.get_session()
        start_time = metrics.start_timer()
        try:
            # Note: DexScreener doesn't have a direct "latest" list in public API V1. 
            # We simulate querying a known list of new contracts or search endpoint.
            # Using a mock search for SOL pairs as a proxy for demonstration.
            async with session.get(f"{self.base_url}/search/?q=sol") as response:
                response.raise_for_status()
                data = await response.json()
                metrics.record_api_call("dexscreener_success", metrics.stop_timer(start_time))
                return data.get("pairs", [])
        except Exception as e:
            metrics.record_api_call("dexscreener_error", metrics.stop_timer(start_time))
            logger.error(f"DexScreener API error: {e}")
            return []

    async def close(self):
        if self.session:
            await self.session.close()

dex_api = DexScreenerAPI()
