import aiohttp
from utils.logger import logger
from config.settings import settings
from system.metrics import metrics

class DexScreenerAPI:
    def __init__(self):
        # Base URL should be: https://api.dexscreener.com/latest/dex
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
            # CORRECT ENDPOINT: /search?q=sol (No /tokens/{token_address}/ in the path)
            url = f"{self.base_url}/search?q=sol"
            
            async with session.get(url) as response:
                response.raise_for_status() # This will raise an exception if status is not 200 OK
                data = await response.json()
                metrics.record_api_call("dexscreener_success", metrics.stop_timer(start_time))
                return data.get("pairs", [])
                
        except aiohttp.ClientResponseError as e:
            metrics.record_api_call("dexscreener_error", metrics.stop_timer(start_time))
            logger.error(f"DexScreener API HTTP error: {e.status}, message='{e.message}', url={e.request_info.real_url}")
            return []
        except Exception as e:
            metrics.record_api_call("dexscreener_error", metrics.stop_timer(start_time))
            logger.error(f"DexScreener API connection error: {e}")
            return []

    async def close(self):
        if self.session:
            await self.session.close()

dex_api = DexScreenerAPI()
