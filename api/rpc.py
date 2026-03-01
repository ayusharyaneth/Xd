import asyncio
from utils.logger import logger

class RPCCLient:
    """Mock RPC Client for fetching deep blockchain data not available on DexScreener"""
    async def get_token_transfers(self, token_address: str):
        # Simulate network delay
        await asyncio.sleep(0.1)
        return [{"from": "0x123", "to": "0x456", "amount": 1000}]
        
    async def get_wallet_funding(self, wallet_address: str):
        await asyncio.sleep(0.05)
        return {"funded_by": "0xBinanceHotWallet", "amount": 10}

rpc_client = RPCCLient()
