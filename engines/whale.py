# ============================================================
# WHALE DETECTION ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, format_currency, shorten_address
from api.dexscreener import TokenPair


logger = get_logger("whale_engine")


@dataclass
class Whale:
    """Represents a detected whale"""
    address: str
    total_value_usd: float
    token_holdings: Dict[str, float] = field(default_factory=dict)
    recent_transactions: List[Dict] = field(default_factory=list)
    first_seen: int = field(default_factory=get_timestamp)
    last_active: int = field(default_factory=get_timestamp)
    classification: str = "unknown"
    activity_score: float = 0.0
    
    @property
    def primary_tokens(self) -> List[str]:
        """Get tokens with largest holdings"""
        sorted_tokens = sorted(
            self.token_holdings.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [t[0] for t in sorted_tokens[:5]]


@dataclass
class WhaleMovement:
    """Represents a whale movement"""
    whale_address: str
    token_address: str
    movement_type: str  # 'buy', 'sell', 'transfer'
    amount_usd: float
    timestamp: int
    price_impact: float
    significance: str  # 'low', 'medium', 'high', 'critical'
    details: Dict[str, Any] = field(default_factory=dict)


class WhaleDetectionEngine:
    """Detect and track whale activity"""
    
    def __init__(self):
        self.config = get_config()
        self.whale_config = self.config.strategy.whale_detection
        self._whales: Dict[str, Whale] = {}
        self._movements: List[WhaleMovement] = []
        self._tracked_tokens: Set[str] = set()
        self._cooldowns: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
    
    async def detect_whales(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]] = None,
        holder_data: Optional[List[Dict]] = None
    ) -> List[Whale]:
        """Detect whales for a specific token"""
        
        whales = []
        thresholds = self.whale_config.thresholds
        
        # Process holder data
        if holder_data:
            for holder in holder_data:
                value = holder.get('value_usd', 0)
                
                if value >= thresholds.min_token_holdings_usd:
                    address = holder.get('address', '')
                    
                    async with self._lock:
                        if address in self._whales:
                            # Update existing whale
                            whale = self._whales[address]
                            whale.token_holdings[pair.token_address] = value
                            whale.last_active = get_timestamp()
                        else:
                            # Create new whale
                            whale = Whale(
                                address=address,
                                total_value_usd=value,
                                token_holdings={pair.token_address: value},
                                classification=self._classify_whales(value)
                            )
                            self._whales[address] = whale
                        
                        whales.append(whale)
        
        # Process transaction data
        if transaction_data:
            for tx in transaction_data:
                amount = tx.get('amount_usd', 0)
                
                if amount >= thresholds.min_single_buy_usd:
                    address = tx.get('buyer') or tx.get('seller', '')
                    
                    async with self._lock:
                        if address in self._whales:
                            whale = self._whales[address]
                            whale.recent_transactions.append({
                                'type': tx.get('type'),
                                'amount': amount,
                                'timestamp': tx.get('timestamp'),
                                'token': pair.token_address
                            })
                            whale.last_active = get_timestamp()
                            
                            # Keep only recent transactions
                            cutoff = get_timestamp() - 86400  # 24 hours
                            whale.recent_transactions = [
                                t for t in whale.recent_transactions
                                if t['timestamp'] > cutoff
                            ]
                        else:
                            # Create whale from transaction
                            whale = Whale(
                                address=address,
                                total_value_usd=amount,
                                classification=self._classify_whales(amount),
                                recent_transactions=[{
                                    'type': tx.get('type'),
                                    'amount': amount,
                                    'timestamp': tx.get('timestamp'),
                                    'token': pair.token_address
                                }]
                            )
                            self._whales[address] = whale
                        
                        if whale not in whales:
                            whales.append(whale)
        
        # Track token
        async with self._lock:
            self._tracked_tokens.add(pair.token_address)
        
        return whales
    
    def _classify_whales(self, value: float) -> str:
        """Classify whale by size"""
        if value >= 500000:
            return "mega_whale"
        elif value >= 100000:
            return "large_whale"
        elif value >= 50000:
            return "whale"
        elif value >= 10000:
            return "shark"
        else:
            return "dolphin"
    
    async def detect_movements(
        self,
        pair: TokenPair,
        transaction_data: List[Dict]
    ) -> List[WhaleMovement]:
        """Detect significant whale movements"""
        
        movements = []
        alert_conditions = self.whale_config.alert_conditions
        
        for tx in transaction_data:
            amount = tx.get('amount_usd', 0)
            tx_type = tx.get('type', '')
            
            # Check for large buy
            if tx_type == 'buy' and amount >= alert_conditions.large_buy.threshold_usd:
                movement = WhaleMovement(
                    whale_address=tx.get('buyer', ''),
                    token_address=pair.token_address,
                    movement_type='buy',
                    amount_usd=amount,
                    timestamp=tx.get('timestamp', get_timestamp()),
                    price_impact=tx.get('price_impact', 0),
                    significance=self._classify_significance(amount),
                    details={
                        'token_symbol': pair.token_symbol,
                        'price': pair.price_usd,
                        'liquidity': pair.liquidity_usd
                    }
                )
                
                # Check cooldown
                cooldown_key = f"buy_{movement.whale_address}_{pair.token_address}"
                if not await self._is_on_cooldown(cooldown_key):
                    movements.append(movement)
                    await self._set_cooldown(
                        cooldown_key,
                        alert_conditions.large_buy.cooldown_seconds
                    )
            
            # Check for large sell
            elif tx_type == 'sell' and amount >= alert_conditions.large_sell.threshold_usd:
                movement = WhaleMovement(
                    whale_address=tx.get('seller', ''),
                    token_address=pair.token_address,
                    movement_type='sell',
                    amount_usd=amount,
                    timestamp=tx.get('timestamp', get_timestamp()),
                    price_impact=tx.get('price_impact', 0),
                    significance=self._classify_significance(amount),
                    details={
                        'token_symbol': pair.token_symbol,
                        'price': pair.price_usd,
                        'liquidity': pair.liquidity_usd
                    }
                )
                
                # Check cooldown
                cooldown_key = f"sell_{movement.whale_address}_{pair.token_address}"
                if not await self._is_on_cooldown(cooldown_key):
                    movements.append(movement)
                    await self._set_cooldown(
                        cooldown_key,
                        alert_conditions.large_sell.cooldown_seconds
                    )
        
        # Store movements
        async with self._lock:
            self._movements.extend(movements)
            # Keep only recent movements
            cutoff = get_timestamp() - 86400
            self._movements = [
                m for m in self._movements
                if m.timestamp > cutoff
            ]
        
        return movements
    
    def _classify_significance(self, amount: float) -> str:
        """Classify movement significance"""
        if amount >= 100000:
            return "critical"
        elif amount >= 50000:
            return "high"
        elif amount >= 20000:
            return "medium"
        else:
            return "low"
    
    async def detect_accumulation(
        self,
        token_address: str,
        window_minutes: int = 30
    ) -> List[Dict[str, Any]]:
        """Detect whale accumulation patterns"""
        
        alert_conditions = self.whale_config.alert_conditions
        threshold_count = alert_conditions.position_accumulation.get('threshold_count', 3)
        
        window_start = get_timestamp() - (window_minutes * 60)
        
        async with self._lock:
            # Get recent movements for token
            token_movements = [
                m for m in self._movements
                if m.token_address == token_address
                and m.timestamp > window_start
                and m.movement_type == 'buy'
            ]
        
        # Group by whale
        whale_buys = defaultdict(list)
        for m in token_movements:
            whale_buys[m.whale_address].append(m)
        
        # Find accumulation patterns
        accumulations = []
        for whale, buys in whale_buys.items():
            if len(buys) >= threshold_count:
                total_amount = sum(b.amount_usd for b in buys)
                accumulations.append({
                    'whale': whale,
                    'buy_count': len(buys),
                    'total_amount': total_amount,
                    'average_buy': total_amount / len(buys),
                    'first_buy': min(b.timestamp for b in buys),
                    'last_buy': max(b.timestamp for b in buys),
                    'significance': self._classify_significance(total_amount)
                })
        
        return accumulations
    
    async def get_whale_activity_summary(
        self,
        token_address: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get summary of whale activity"""
        
        cutoff = get_timestamp() - (hours * 3600)
        
        async with self._lock:
            if token_address:
                movements = [
                    m for m in self._movements
                    if m.token_address == token_address and m.timestamp > cutoff
                ]
            else:
                movements = [m for m in self._movements if m.timestamp > cutoff]
        
        # Calculate metrics
        total_buy_volume = sum(
            m.amount_usd for m in movements if m.movement_type == 'buy'
        )
        total_sell_volume = sum(
            m.amount_usd for m in movements if m.movement_type == 'sell'
        )
        
        unique_whales = set(m.whale_address for m in movements)
        
        buy_count = sum(1 for m in movements if m.movement_type == 'buy')
        sell_count = sum(1 for m in movements if m.movement_type == 'sell')
        
        # Net flow
        net_flow = total_buy_volume - total_sell_volume
        
        return {
            'total_whales': len(unique_whales),
            'total_movements': len(movements),
            'buy_volume': round(total_buy_volume, 2),
            'sell_volume': round(total_sell_volume, 2),
            'net_flow': round(net_flow, 2),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'buy_sell_ratio': round(buy_count / max(1, sell_count), 2),
            'significant_movements': [
                {
                    'whale': shorten_address(m.whale_address),
                    'type': m.movement_type,
                    'amount': format_currency(m.amount_usd),
                    'significance': m.significance,
                    'time_ago': get_timestamp() - m.timestamp
                }
                for m in sorted(movements, key=lambda x: x.amount_usd, reverse=True)[:5]
            ]
        }
    
    async def get_whale_profile(
        self,
        whale_address: str
    ) -> Optional[Dict[str, Any]]:
        """Get detailed profile of a whale"""
        
        async with self._lock:
            whale = self._whales.get(whale_address)
        
        if not whale:
            return None
        
        # Get recent movements
        recent_movements = [
            m for m in self._movements
            if m.whale_address == whale_address
        ]
        
        # Calculate metrics
        total_buys = sum(1 for m in recent_movements if m.movement_type == 'buy')
        total_sells = sum(1 for m in recent_movements if m.movement_type == 'sell')
        
        buy_volume = sum(m.amount_usd for m in recent_movements if m.movement_type == 'buy')
        sell_volume = sum(m.amount_usd for m in recent_movements if m.movement_type == 'sell')
        
        return {
            'address': shorten_address(whale.address),
            'classification': whale.classification,
            'total_value': format_currency(whale.total_value_usd),
            'token_count': len(whale.token_holdings),
            'primary_tokens': whale.primary_tokens[:5],
            'activity_score': round(whale.activity_score, 2),
            'first_seen': whale.first_seen,
            'last_active': whale.last_active,
            'recent_stats': {
                'total_buys': total_buys,
                'total_sells': total_sells,
                'buy_volume': format_currency(buy_volume),
                'sell_volume': format_currency(sell_volume),
                'net_flow': format_currency(buy_volume - sell_volume)
            },
            'recent_transactions': whale.recent_transactions[-10:]
        }
    
    async def _is_on_cooldown(self, key: str) -> bool:
        """Check if key is on cooldown"""
        async with self._lock:
            return get_timestamp() < self._cooldowns.get(key, 0)
    
    async def _set_cooldown(self, key: str, duration_seconds: int):
        """Set cooldown for key"""
        async with self._lock:
            self._cooldowns[key] = get_timestamp() + duration_seconds
    
    async def cleanup(self):
        """Clean up old data"""
        cutoff = get_timestamp() - 86400  # 24 hours
        
        async with self._lock:
            # Clean old movements
            self._movements = [m for m in self._movements if m.timestamp > cutoff]
            
            # Clean inactive whales
            inactive_whales = [
                addr for addr, whale in self._whales.items()
                if whale.last_active < cutoff
            ]
            for addr in inactive_whales:
                del self._whales[addr]
            
            # Clean expired cooldowns
            current_time = get_timestamp()
            expired = [k for k, v in self._cooldowns.items() if current_time > v]
            for k in expired:
                del self._cooldowns[k]


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_whale_engine: Optional[WhaleDetectionEngine] = None


def get_whale_engine() -> WhaleDetectionEngine:
    """Get or create whale detection engine singleton"""
    global _whale_engine
    if _whale_engine is None:
        _whale_engine = WhaleDetectionEngine()
    return _whale_engine
