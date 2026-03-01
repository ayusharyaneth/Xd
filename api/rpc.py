# ============================================================
# RPC CLIENT FOR BLOCKCHAIN DATA
# ============================================================

import asyncio
from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass
import aiohttp
from aiohttp import ClientTimeout, ClientSession
import json
import base58

from config.settings import get_config
from utils.logger import get_logger, log_execution_time
from utils.helpers import RateLimiter, retry_with_backoff, get_timestamp


logger = get_logger("rpc")


@dataclass
class TokenAccount:
    """Represents a token account"""
    address: str
    owner: str
    mint: str
    balance: float
    decimals: int = 9
    
    @property
    def balance_raw(self) -> int:
        """Get raw balance without decimals"""
        return int(self.balance * (10 ** self.decimals))


@dataclass
class TransactionInfo:
    """Represents transaction information"""
    signature: str
    timestamp: int
    slot: int
    success: bool
    fee: float
    instructions: List[Dict] = None
    token_transfers: List[Dict] = None
    
    def __post_init__(self):
        if self.instructions is None:
            self.instructions = []
        if self.token_transfers is None:
            self.token_transfers = []


@dataclass
class WalletInfo:
    """Represents wallet information"""
    address: str
    sol_balance: float
    token_accounts: List[TokenAccount] = None
    transaction_count: int = 0
    first_transaction: Optional[int] = None
    last_transaction: Optional[int] = None
    
    def __post_init__(self):
        if self.token_accounts is None:
            self.token_accounts = []
    
    @property
    def wallet_age_days(self) -> float:
        """Calculate wallet age in days"""
        if not self.first_transaction:
            return 0.0
        return (get_timestamp() - self.first_transaction) / 86400
    
    @property
    def is_new_wallet(self) -> bool:
        """Check if wallet is new (less than 7 days)"""
        return self.wallet_age_days < 7


class SolanaRPCClient:
    """Async client for Solana RPC"""
    
    def __init__(self):
        self.config = get_config()
        self.primary_endpoint = self.config.settings.RPC_ENDPOINT
        self.backup_endpoint = self.config.settings.RPC_BACKUP_ENDPOINT
        self.current_endpoint = self.primary_endpoint
        
        self.session: Optional[ClientSession] = None
        self.rate_limiter = RateLimiter(max_calls=100, window_seconds=60)
        self._request_count = 0
        self._error_count = 0
        self._failover_count = 0
        self._lock = asyncio.Lock()
    
    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30, connect=10)
            self.session = ClientSession(
                timeout=timeout,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'DexIntelBot/1.0'
                }
            )
        return self.session
    
    async def close(self):
        """Close the HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def _switch_endpoint(self):
        """Switch to backup endpoint"""
        if self.current_endpoint == self.primary_endpoint:
            self.current_endpoint = self.backup_endpoint
            self._failover_count += 1
            logger.warning(f"Switched to backup RPC endpoint: {self.backup_endpoint}")
        else:
            self.current_endpoint = self.primary_endpoint
            logger.info(f"Switched back to primary RPC endpoint: {self.primary_endpoint}")
    
    async def _make_request(
        self,
        method: str,
        params: Optional[List] = None
    ) -> Optional[Any]:
        """Make RPC request with retry and failover"""
        await self.rate_limiter.acquire()
        
        session = await self._get_session()
        
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_count,
            "method": method,
            "params": params or []
        }
        
        async with self._lock:
            self._request_count += 1
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.post(
                    self.current_endpoint,
                    json=payload
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'error' in data:
                            logger.error(f"RPC error: {data['error']}")
                            return None
                        return data.get('result')
                    elif response.status == 429:
                        logger.warning("RPC rate limit hit")
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error(f"RPC HTTP error: {response.status}")
                        if attempt < max_retries - 1:
                            self._switch_endpoint()
            except aiohttp.ClientError as e:
                logger.error(f"RPC client error: {e}")
                if attempt < max_retries - 1:
                    self._switch_endpoint()
                    await asyncio.sleep(1)
            except asyncio.TimeoutError:
                logger.error("RPC timeout")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"RPC unexpected error: {e}")
                return None
        
        async with self._lock:
            self._error_count += 1
        return None
    
    @log_execution_time("DEBUG")
    async def get_balance(self, address: str) -> float:
        """Get SOL balance for address"""
        result = await self._make_request("getBalance", [address])
        if result and 'value' in result:
            return result['value'] / 1_000_000_000  # Convert lamports to SOL
        return 0.0
    
    @log_execution_time("DEBUG")
    async def get_token_accounts(
        self,
        owner: str,
        mint: Optional[str] = None
    ) -> List[TokenAccount]:
        """Get token accounts for owner"""
        filters = {"mint": mint} if mint else {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}
        
        params = [
            owner,
            filters,
            {"encoding": "jsonParsed"}
        ]
        
        result = await self._make_request("getTokenAccountsByOwner", params)
        if not result or 'value' not in result:
            return []
        
        accounts = []
        for acc in result['value']:
            try:
                parsed = acc['account']['data']['parsed']['info']
                accounts.append(TokenAccount(
                    address=acc['pubkey'],
                    owner=parsed['owner'],
                    mint=parsed['mint'],
                    balance=float(parsed['tokenAmount']['uiAmount'] or 0),
                    decimals=parsed['tokenAmount']['decimals']
                ))
            except (KeyError, TypeError) as e:
                logger.debug(f"Error parsing token account: {e}")
                continue
        
        return accounts
    
    @log_execution_time("DEBUG")
    async def get_account_info(self, address: str) -> Optional[Dict]:
        """Get account information"""
        params = [address, {"encoding": "jsonParsed"}]
        result = await self._make_request("getAccountInfo", params)
        if result and 'value' in result:
            return result['value']
        return None
    
    @log_execution_time("DEBUG")
    async def get_transaction(
        self,
        signature: str,
        max_supported_transaction_version: int = 0
    ) -> Optional[TransactionInfo]:
        """Get transaction details"""
        params = [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": max_supported_transaction_version
            }
        ]
        
        result = await self._make_request("getTransaction", params)
        if not result:
            return None
        
        try:
            meta = result.get('meta', {})
            block_time = result.get('blockTime', 0)
            
            # Extract token transfers
            token_transfers = []
            if 'meta' in result and 'postTokenBalances' in meta:
                pre_balances = {b['accountIndex']: b for b in meta.get('preTokenBalances', [])}
                post_balances = {b['accountIndex']: b for b in meta.get('postTokenBalances', [])}
                
                for idx, post in post_balances.items():
                    pre = pre_balances.get(idx, {})
                    pre_amount = float(pre.get('uiTokenAmount', {}).get('uiAmount', 0) or 0)
                    post_amount = float(post.get('uiTokenAmount', {}).get('uiAmount', 0) or 0)
                    
                    if pre_amount != post_amount:
                        token_transfers.append({
                            'mint': post.get('mint'),
                            'owner': post.get('owner'),
                            'change': post_amount - pre_amount
                        })
            
            return TransactionInfo(
                signature=signature,
                timestamp=block_time,
                slot=result.get('slot', 0),
                success=not meta.get('err'),
                fee=meta.get('fee', 0) / 1_000_000_000,
                instructions=result.get('transaction', {}).get('message', {}).get('instructions', []),
                token_transfers=token_transfers
            )
        except Exception as e:
            logger.error(f"Error parsing transaction: {e}")
            return None
    
    @log_execution_time("DEBUG")
    async def get_signatures_for_address(
        self,
        address: str,
        limit: int = 100,
        before: Optional[str] = None
    ) -> List[Dict]:
        """Get transaction signatures for address"""
        params = [address, {"limit": limit}]
        if before:
            params[1]['before'] = before
        
        result = await self._make_request("getSignaturesForAddress", params)
        return result or []
    
    @log_execution_time("DEBUG")
    async def get_wallet_info(self, address: str) -> Optional[WalletInfo]:
        """Get comprehensive wallet information"""
        try:
            # Get SOL balance
            sol_balance = await self.get_balance(address)
            
            # Get token accounts
            token_accounts = await self.get_token_accounts(address)
            
            # Get transaction signatures
            signatures = await self.get_signatures_for_address(address, limit=1000)
            
            first_tx = None
            last_tx = None
            if signatures:
                first_tx = signatures[-1].get('blockTime')
                last_tx = signatures[0].get('blockTime')
            
            return WalletInfo(
                address=address,
                sol_balance=sol_balance,
                token_accounts=token_accounts,
                transaction_count=len(signatures),
                first_transaction=first_tx,
                last_transaction=last_tx
            )
        except Exception as e:
            logger.error(f"Error getting wallet info: {e}")
            return None
    
    @log_execution_time("DEBUG")
    async def get_multiple_accounts(
        self,
        addresses: List[str]
    ) -> List[Optional[Dict]]:
        """Get multiple account infos in batch"""
        params = [addresses, {"encoding": "jsonParsed"}]
        result = await self._make_request("getMultipleAccounts", params)
        if result and 'value' in result:
            return result['value']
        return [None] * len(addresses)
    
    @log_execution_time("DEBUG")
    async def get_slot(self) -> int:
        """Get current slot"""
        result = await self._make_request("getSlot")
        return result or 0
    
    @log_execution_time("DEBUG")
    async def get_block_time(self, slot: int) -> Optional[int]:
        """Get block time for slot"""
        result = await self._make_request("getBlockTime", [slot])
        return result
    
    @log_execution_time("DEBUG")
    async def get_recent_blockhash(self) -> Optional[str]:
        """Get recent blockhash"""
        result = await self._make_request("getLatestBlockhash")
        if result and 'value' in result:
            return result['value'].get('blockhash')
        return None
    
    @log_execution_time("DEBUG")
    async def get_token_supply(self, mint: str) -> Optional[Dict]:
        """Get token supply"""
        result = await self._make_request("getTokenSupply", [mint])
        if result and 'value' in result:
            return result['value']
        return None
    
    @log_execution_time("DEBUG")
    async def get_largest_token_accounts(
        self,
        mint: str,
        limit: int = 20
    ) -> List[Dict]:
        """Get largest token holders"""
        params = [mint, {"limit": limit}]
        result = await self._make_request("getTokenLargestAccounts", params)
        if result and 'value' in result:
            return result['value']
        return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RPC client statistics"""
        return {
            'total_requests': self._request_count,
            'total_errors': self._error_count,
            'error_rate': self._error_count / max(1, self._request_count),
            'failover_count': self._failover_count,
            'current_endpoint': self.current_endpoint,
            'rate_limit_remaining': asyncio.run_coroutine_threadsafe(
                self.rate_limiter.get_remaining(), asyncio.get_event_loop()
            ).result() if self._request_count > 0 else self.rate_limiter.max_calls
        }


# ============================================================
# WALLET ANALYZER
# ============================================================

class WalletAnalyzer:
    """Analyze wallet behavior and patterns"""
    
    def __init__(self, rpc_client: SolanaRPCClient):
        self.rpc = rpc_client
    
    async def analyze_wallet_funding(
        self,
        wallet_address: str,
        lookback_days: int = 7
    ) -> Dict[str, Any]:
        """Analyze wallet funding sources"""
        signatures = await self.rpc.get_signatures_for_address(
            wallet_address,
            limit=100
        )
        
        funding_sources = set()
        funding_timestamps = []
        
        for sig_info in signatures:
            if sig_info.get('err'):
                continue
            
            tx = await self.rpc.get_transaction(sig_info['signature'])
            if not tx:
                continue
            
            # Check if this is a funding transaction (SOL transfer in)
            for transfer in tx.token_transfers:
                if transfer.get('change', 0) > 0:
                    funding_sources.add(transfer.get('owner', 'unknown'))
                    funding_timestamps.append(tx.timestamp)
        
        return {
            'funding_sources': list(funding_sources),
            'funding_count': len(funding_timestamps),
            'first_funding': min(funding_timestamps) if funding_timestamps else None,
            'funding_pattern': self._analyze_pattern(funding_timestamps)
        }
    
    def _analyze_pattern(self, timestamps: List[int]) -> str:
        """Analyze timing pattern of transactions"""
        if len(timestamps) < 2:
            return "insufficient_data"
        
        intervals = [
            timestamps[i] - timestamps[i+1]
            for i in range(len(timestamps) - 1)
        ]
        
        avg_interval = sum(intervals) / len(intervals)
        variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
        
        # Low variance suggests automated/coordinated activity
        if variance < 60:  # Less than 1 minute variance
            return "highly_regular"
        elif variance < 300:  # Less than 5 minutes variance
            return "somewhat_regular"
        else:
            return "irregular"
    
    async def detect_wallet_clusters(
        self,
        wallet_addresses: List[str]
    ) -> List[List[str]]:
        """Detect clusters of related wallets"""
        funding_analysis = {}
        
        for address in wallet_addresses:
            funding_analysis[address] = await self.analyze_wallet_funding(address)
        
        # Group wallets by shared funding sources
        clusters = []
        processed = set()
        
        for addr1 in wallet_addresses:
            if addr1 in processed:
                continue
            
            cluster = [addr1]
            sources1 = set(funding_analysis[addr1]['funding_sources'])
            
            for addr2 in wallet_addresses:
                if addr2 == addr1 or addr2 in processed:
                    continue
                
                sources2 = set(funding_analysis[addr2]['funding_sources'])
                overlap = sources1 & sources2
                
                if len(overlap) > 0:
                    cluster.append(addr2)
                    processed.add(addr2)
            
            if len(cluster) > 1:
                clusters.append(cluster)
            processed.add(addr1)
        
        return clusters


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_rpc_client: Optional[SolanaRPCClient] = None


def get_rpc_client() -> SolanaRPCClient:
    """Get or create RPC client singleton"""
    global _rpc_client
    if _rpc_client is None:
        _rpc_client = SolanaRPCClient()
    return _rpc_client


async def close_rpc_client():
    """Close RPC client"""
    global _rpc_client
    if _rpc_client:
        await _rpc_client.close()
        _rpc_client = None
