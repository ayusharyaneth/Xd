# ============================================================
# DEVELOPER REPUTATION TRACKING ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, shorten_address
from api.dexscreener import TokenPair
from api.rpc import SolanaRPCClient


logger = get_logger("developer_engine")


@dataclass
class DeveloperReputation:
    """Developer reputation score"""
    score: float  # 0-100
    classification: str  # trusted, neutral, suspicious, blacklist
    previous_tokens: int
    successful_tokens: int
    rugged_tokens: int
    avg_token_lifetime_days: float
    liquidity_lock_rate: float
    red_flags: List[str] = field(default_factory=list)
    green_flags: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenHistory:
    """History of a token launched by developer"""
    token_address: str
    name: str
    symbol: str
    launch_date: int
    end_date: Optional[int]
    peak_market_cap: float
    final_market_cap: float
    liquidity_locked: bool
    lock_duration_days: int
    is_rug: bool
    rug_type: Optional[str]
    current_status: str


class DeveloperReputationEngine:
    """Track and analyze developer reputation"""
    
    def __init__(self):
        self.config = get_config()
        self.dev_config = self.config.strategy.developer_reputation
        self._reputation_cache: Dict[str, DeveloperReputation] = {}
        self._token_history: Dict[str, List[TokenHistory]] = defaultdict(list)
        self._developer_tokens: Dict[str, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()
    
    async def analyze_developer(
        self,
        pair: TokenPair,
        contract_data: Optional[Dict] = None,
        rpc_client: Optional[SolanaRPCClient] = None
    ) -> DeveloperReputation:
        """Analyze developer reputation for a token"""
        
        # Try to identify developer
        dev_address = await self._identify_developer(pair, contract_data, rpc_client)
        
        if not dev_address:
            return self._create_unknown_reputation()
        
        # Check cache
        cache_key = f"{dev_address}_{get_timestamp() // 3600}"  # Cache for 1 hour
        async with self._lock:
            if cache_key in self._reputation_cache:
                return self._reputation_cache[cache_key]
        
        # Get or build token history
        history = await self._get_token_history(dev_address, rpc_client)
        
        # Calculate reputation score
        reputation = await self._calculate_reputation(dev_address, history)
        
        # Cache result
        async with self._lock:
            self._reputation_cache[cache_key] = reputation
        
        return reputation
    
    async def _identify_developer(
        self,
        pair: TokenPair,
        contract_data: Optional[Dict],
        rpc_client: Optional[SolanaRPCClient]
    ) -> Optional[str]:
        """Identify the developer wallet address"""
        
        # Try contract data first
        if contract_data:
            deployer = contract_data.get('deployer')
            if deployer:
                return deployer
            
            creator = contract_data.get('creator')
            if creator:
                return creator
        
        # Try to get from pair data
        if pair.pair_created_at:
            # If we have RPC client, try to find creator
            if rpc_client:
                try:
                    # Get signatures for token mint
                    signatures = await rpc_client.get_signatures_for_address(
                        pair.token_address,
                        limit=10
                    )
                    
                    if signatures:
                        # The earliest signature likely belongs to creator
                        oldest_sig = signatures[-1]
                        tx = await rpc_client.get_transaction(oldest_sig['signature'])
                        if tx:
                            # Extract creator from transaction
                            for instruction in tx.instructions:
                                if 'parsed' in instruction:
                                    info = instruction['parsed'].get('info', {})
                                    if 'source' in info:
                                        return info['source']
                except Exception as e:
                    logger.debug(f"Error identifying developer: {e}")
        
        return None
    
    async def _get_token_history(
        self,
        dev_address: str,
        rpc_client: Optional[SolanaRPCClient]
    ) -> List[TokenHistory]:
        """Get token launch history for developer"""
        
        # Check if we already have history
        async with self._lock:
            if dev_address in self._token_history:
                return self._token_history[dev_address]
        
        # If we have RPC access, try to build history
        if rpc_client:
            try:
                history = await self._build_history_from_chain(dev_address, rpc_client)
                async with self._lock:
                    self._token_history[dev_address] = history
                return history
            except Exception as e:
                logger.debug(f"Error building history: {e}")
        
        return []
    
    async def _build_history_from_chain(
        self,
        dev_address: str,
        rpc_client: SolanaRPCClient
    ) -> List[TokenHistory]:
        """Build token history from blockchain data"""
        history = []
        
        try:
            # Get all transactions for developer
            signatures = await rpc_client.get_signatures_for_address(
                dev_address,
                limit=1000
            )
            
            # Look for token creation transactions
            token_creations = []
            for sig_info in signatures:
                tx = await rpc_client.get_transaction(sig_info['signature'])
                if not tx:
                    continue
                
                # Check if this is a token creation
                for instruction in tx.instructions:
                    if self._is_token_creation(instruction):
                        token_creations.append({
                            'signature': sig_info['signature'],
                            'timestamp': tx.timestamp,
                            'instruction': instruction
                        })
            
            # Build history for each token
            for creation in token_creations:
                token_history = await self._analyze_token_lifecycle(
                    creation,
                    rpc_client
                )
                if token_history:
                    history.append(token_history)
        
        except Exception as e:
            logger.error(f"Error building history from chain: {e}")
        
        return history
    
    def _is_token_creation(self, instruction: Dict) -> bool:
        """Check if instruction is a token creation"""
        # Check for token program initialization
        program_id = instruction.get('programId', '')
        if program_id == 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA':
            parsed = instruction.get('parsed', {})
            if parsed.get('type') in ['initializeMint', 'createAccount']:
                return True
        
        # Check for Metaplex token metadata
        if 'meta' in program_id.lower() or 'mpl' in program_id.lower():
            return True
        
        return False
    
    async def _analyze_token_lifecycle(
        self,
        creation: Dict,
        rpc_client: SolanaRPCClient
    ) -> Optional[TokenHistory]:
        """Analyze the lifecycle of a token"""
        try:
            # Extract token info from creation
            instruction = creation['instruction']
            parsed = instruction.get('parsed', {})
            info = parsed.get('info', {})
            
            token_address = info.get('mint') or info.get('newAccount')
            if not token_address:
                return None
            
            # Get current token state
            token_supply = await rpc_client.get_token_supply(token_address)
            
            # Determine if rugged
            is_rug = False
            rug_type = None
            
            if token_supply:
                supply = token_supply.get('uiAmount', 0)
                if supply == 0:
                    is_rug = True
                    rug_type = "supply_burned"
            
            # Check liquidity
            largest_accounts = await rpc_client.get_largest_token_accounts(token_address)
            liquidity_locked = len(largest_accounts) > 0
            
            return TokenHistory(
                token_address=token_address,
                name="Unknown",
                symbol="UNKNOWN",
                launch_date=creation['timestamp'],
                end_date=None if not is_rug else get_timestamp(),
                peak_market_cap=0,
                final_market_cap=0,
                liquidity_locked=liquidity_locked,
                lock_duration_days=0,
                is_rug=is_rug,
                rug_type=rug_type,
                current_status="active" if not is_rug else "rugged"
            )
        
        except Exception as e:
            logger.debug(f"Error analyzing token lifecycle: {e}")
            return None
    
    async def _calculate_reputation(
        self,
        dev_address: str,
        history: List[TokenHistory]
    ) -> DeveloperReputation:
        """Calculate reputation score from history"""
        
        if not history:
            return self._create_unknown_reputation()
        
        score = 50  # Start neutral
        red_flags = []
        green_flags = []
        details = {}
        
        # Count statistics
        total_tokens = len(history)
        rugged_tokens = sum(1 for h in history if h.is_rug)
        successful_tokens = sum(1 for h in history if not h.is_rug and h.peak_market_cap > 100000)
        
        # Calculate average lifetime
        lifetimes = []
        for h in history:
            if h.end_date:
                lifetime = (h.end_date - h.launch_date) / 86400
            else:
                lifetime = (get_timestamp() - h.launch_date) / 86400
            lifetimes.append(lifetime)
        
        avg_lifetime = sum(lifetimes) / len(lifetimes) if lifetimes else 0
        
        # Liquidity lock rate
        locked_count = sum(1 for h in history if h.liquidity_locked)
        lock_rate = locked_count / total_tokens if total_tokens > 0 else 0
        
        # Apply scoring factors
        scoring = self.dev_config.scoring_factors
        
        # Penalty for rugs
        rug_penalty = rugged_tokens * scoring.get('previous_rug_count', -50)
        score += rug_penalty
        if rugged_tokens > 0:
            red_flags.append(f"{rugged_tokens} previous rug pulls")
        
        # Bonus for successful tokens
        success_bonus = successful_tokens * scoring.get('previous_success_rate', 30)
        score += success_bonus
        if successful_tokens > 0:
            green_flags.append(f"{successful_tokens} successful previous tokens")
        
        # Liquidity lock bonus
        lock_bonus = lock_rate * scoring.get('liquidity_lock_percentage', 20)
        score += lock_bonus
        if lock_rate > 0.8:
            green_flags.append("Consistently locks liquidity")
        elif lock_rate < 0.3:
            red_flags.append("Rarely locks liquidity")
        
        # Token lifetime factor
        if avg_lifetime > 30:
            score += 10
            green_flags.append("Tokens have good longevity")
        elif avg_lifetime < 7:
            score -= 10
            red_flags.append("Tokens typically short-lived")
        
        # Check red flags from config
        for flag in self.dev_config.red_flags:
            if flag in red_flags:
                score -= 15
        
        # Determine classification
        classification = self._classify_score(score)
        
        details = {
            'total_tokens': total_tokens,
            'rugged_tokens': rugged_tokens,
            'successful_tokens': successful_tokens,
            'avg_lifetime_days': round(avg_lifetime, 2),
            'liquidity_lock_rate': round(lock_rate, 2),
            'developer_address': shorten_address(dev_address)
        }
        
        return DeveloperReputation(
            score=max(0, min(100, score)),
            classification=classification,
            previous_tokens=total_tokens,
            successful_tokens=successful_tokens,
            rugged_tokens=rugged_tokens,
            avg_token_lifetime_days=round(avg_lifetime, 2),
            liquidity_lock_rate=round(lock_rate, 2),
            red_flags=red_flags,
            green_flags=green_flags,
            details=details
        )
    
    def _classify_score(self, score: float) -> str:
        """Classify reputation score"""
        thresholds = self.dev_config.reputation_thresholds
        
        if score >= thresholds.get('trusted', 80):
            return "trusted"
        elif score >= thresholds.get('neutral', 50):
            return "neutral"
        elif score >= thresholds.get('suspicious', 25):
            return "suspicious"
        else:
            return "blacklist"
    
    def _create_unknown_reputation(self) -> DeveloperReputation:
        """Create reputation for unknown developer"""
        return DeveloperReputation(
            score=50,
            classification="unknown",
            previous_tokens=0,
            successful_tokens=0,
            rugged_tokens=0,
            avg_token_lifetime_days=0,
            liquidity_lock_rate=0,
            red_flags=["Developer identity unknown"],
            green_flags=[],
            details={'note': 'Insufficient data to analyze developer'}
        )
    
    async def track_token_launch(
        self,
        dev_address: str,
        token_address: str,
        pair: TokenPair
    ):
        """Track a new token launch by developer"""
        async with self._lock:
            self._developer_tokens[dev_address].add(token_address)
    
    async def get_developer_stats(
        self,
        dev_address: str
    ) -> Dict[str, Any]:
        """Get statistics for a developer"""
        async with self._lock:
            tokens = self._developer_tokens.get(dev_address, set())
            history = self._token_history.get(dev_address, [])
        
        return {
            'total_tokens_launched': len(tokens),
            'tracked_tokens': len(history),
            'known_tokens': list(tokens)[:10],  # Limit output
            'has_history': len(history) > 0
        }
    
    async def check_red_flags(
        self,
        pair: TokenPair,
        contract_data: Optional[Dict]
    ) -> List[str]:
        """Check for red flags in token"""
        red_flags = []
        
        if not contract_data:
            return ["Contract not verified"]
        
        # Check contract functions
        functions = contract_data.get('functions', [])
        
        dangerous_functions = {
            'mint': "Mint function present - supply can be inflated",
            'burn': "Burn function present",
            'pause': "Trading can be paused",
            'blacklist': "Blacklist function present",
            'setTax': "Tax can be changed arbitrarily",
            'transferOwnership': "Ownership can be transferred"
        }
        
        for func, warning in dangerous_functions.items():
            if func in functions:
                red_flags.append(warning)
        
        # Check ownership
        if contract_data.get('owner_renounced', False):
            pass  # Good
        else:
            owner = contract_data.get('owner', '')
            if owner:
                red_flags.append(f"Contract has owner: {shorten_address(owner)}")
        
        # Check liquidity lock
        if not contract_data.get('liquidity_locked', False):
            red_flags.append("Liquidity not locked")
        
        return red_flags


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_developer_engine: Optional[DeveloperReputationEngine] = None


def get_developer_engine() -> DeveloperReputationEngine:
    """Get or create developer reputation engine singleton"""
    global _developer_engine
    if _developer_engine is None:
        _developer_engine = DeveloperReputationEngine()
    return _developer_engine
