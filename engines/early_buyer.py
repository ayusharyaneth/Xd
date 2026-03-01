# ============================================================
# EARLY BUYER TRACKING ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, format_currency, shorten_address
from api.dexscreener import TokenPair


logger = get_logger("early_buyer_engine")


@dataclass
class EarlyBuyer:
    """Represents an early buyer"""
    address: str
    entry_price: float
    entry_timestamp: int
    initial_investment: float
    token_amount: float
    position_rank: int
    
    # Tracking fields
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    pnl_percentage: float = 0.0
    has_sold: bool = False
    sell_percentage: float = 0.0
    last_update: int = field(default_factory=get_timestamp)


@dataclass
class EarlyBuyerAnalysis:
    """Analysis of early buyers"""
    token_address: str
    total_early_buyers: int
    tracked_buyers: int
    avg_entry_price: float
    current_price: float
    avg_pnl_percentage: float
    profit_takers_count: int
    diamond_hands_count: int
    distribution_score: float
    risk_indicators: List[str]
    buyer_breakdown: Dict[str, Any]


class EarlyBuyerTracker:
    """Track and analyze early buyers"""
    
    def __init__(self):
        self.config = get_config()
        self.early_config = self.config.strategy.early_buyer
        self._early_buyers: Dict[str, List[EarlyBuyer]] = defaultdict(list)
        self._tracked_tokens: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
    
    async def track_early_buyers(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]] = None
    ) -> List[EarlyBuyer]:
        """Track early buyers for a token"""
        
        token_address = pair.token_address
        tracking_config = self.early_config.tracking
        
        # Get existing tracked buyers
        async with self._lock:
            existing = self._early_buyers.get(token_address, [])
        
        # If we have enough buyers and token is old enough, just return existing
        if len(existing) >= tracking_config.first_n_buyers:
            token_age = (get_timestamp() - (pair.pair_created_at or 0)) / 60
            if token_age > tracking_config.track_duration_minutes:
                return existing
        
        # Process new transaction data
        if transaction_data:
            # Sort by timestamp (oldest first)
            sorted_txs = sorted(
                transaction_data,
                key=lambda x: x.get('timestamp', 0)
            )
            
            for i, tx in enumerate(sorted_txs):
                if tx.get('type') != 'buy':
                    continue
                
                # Check if we've tracked enough buyers
                if len(existing) >= tracking_config.first_n_buyers:
                    break
                
                buyer_address = tx.get('buyer', '')
                
                # Check if already tracked
                if any(b.address == buyer_address for b in existing):
                    continue
                
                # Create early buyer record
                early_buyer = EarlyBuyer(
                    address=buyer_address,
                    entry_price=tx.get('price', pair.price_usd),
                    entry_timestamp=tx.get('timestamp', pair.pair_created_at or get_timestamp()),
                    initial_investment=tx.get('amount_usd', 0),
                    token_amount=tx.get('token_amount', 0),
                    position_rank=len(existing) + 1
                )
                
                async with self._lock:
                    self._early_buyers[token_address].append(early_buyer)
                    existing = self._early_buyers[token_address]
        
        # Update PnL for existing buyers
        await self._update_pnl(token_address, pair.price_usd)
        
        return existing
    
    async def _update_pnl(self, token_address: str, current_price: float):
        """Update PnL for all tracked buyers"""
        
        async with self._lock:
            buyers = self._early_buyers.get(token_address, [])
            
            for buyer in buyers:
                if buyer.entry_price > 0:
                    buyer.pnl_percentage = (
                        (current_price - buyer.entry_price) / buyer.entry_price * 100
                    )
                    buyer.unrealized_pnl = (
                        buyer.initial_investment * (buyer.pnl_percentage / 100)
                    )
                
                buyer.last_update = get_timestamp()
    
    async def analyze_early_buyers(
        self,
        token_address: str,
        current_price: float
    ) -> Optional[EarlyBuyerAnalysis]:
        """Analyze early buyer behavior"""
        
        async with self._lock:
            buyers = self._early_buyers.get(token_address, [])
        
        if not buyers:
            return None
        
        # Calculate metrics
        total_buyers = len(buyers)
        
        avg_entry = sum(b.entry_price for b in buyers) / total_buyers
        
        pnl_values = [b.pnl_percentage for b in buyers]
        avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0
        
        # Count profit takers
        profit_takers = sum(1 for b in buyers if b.has_sold and b.realized_pnl > 0)
        
        # Count diamond hands (holding despite profit)
        diamond_hands = sum(
            1 for b in buyers
            if not b.has_sold and b.pnl_percentage > 50
        )
        
        # Calculate distribution score
        distribution_score = self._calculate_distribution_score(buyers)
        
        # Identify risk indicators
        risk_indicators = self._identify_risk_indicators(buyers)
        
        # Buyer breakdown
        buyer_breakdown = {
            'in_profit': sum(1 for b in buyers if b.pnl_percentage > 0),
            'in_loss': sum(1 for b in buyers if b.pnl_percentage < 0),
            'sold_partially': sum(1 for b in buyers if 0 < b.sell_percentage < 100),
            'sold_fully': sum(1 for b in buyers if b.sell_percentage >= 100),
            'holding': sum(1 for b in buyers if b.sell_percentage == 0)
        }
        
        return EarlyBuyerAnalysis(
            token_address=token_address,
            total_early_buyers=total_buyers,
            tracked_buyers=total_buyers,
            avg_entry_price=round(avg_entry, 8),
            current_price=round(current_price, 8),
            avg_pnl_percentage=round(avg_pnl, 2),
            profit_takers_count=profit_takers,
            diamond_hands_count=diamond_hands,
            distribution_score=round(distribution_score, 2),
            risk_indicators=risk_indicators,
            buyer_breakdown=buyer_breakdown
        )
    
    def _calculate_distribution_score(self, buyers: List[EarlyBuyer]) -> float:
        """Calculate how distributed the early buying was (0-1)"""
        
        if len(buyers) < 2:
            return 0.5
        
        investments = [b.initial_investment for b in buyers]
        total = sum(investments)
        
        if total == 0:
            return 0.5
        
        # Calculate concentration (Gini coefficient approximation)
        sorted_investments = sorted(investments)
        n = len(sorted_investments)
        
        cumsum = 0
        for i, val in enumerate(sorted_investments):
            cumsum += (i + 1) * val
        
        gini = (2 * cumsum) / (n * total) - (n + 1) / n
        
        # Convert to distribution score (1 - Gini)
        return max(0, min(1, 1 - gini))
    
    def _identify_risk_indicators(self, buyers: List[EarlyBuyer]) -> List[str]:
        """Identify risk indicators from early buyer behavior"""
        
        indicators = []
        thresholds = self.early_config.thresholds
        
        # Check for mass selling
        sold_count = sum(1 for b in buyers if b.has_sold)
        if sold_count > 0:
            sell_percentage = sold_count / len(buyers) * 100
            if sell_percentage > thresholds.distribution_warning_percent:
                indicators.append(
                    f"High sell-off: {sell_percentage:.1f}% of early buyers sold"
                )
        
        # Check for early profit taking
        early_sellers = sum(
            1 for b in buyers
            if b.has_sold and b.entry_timestamp > get_timestamp() - 3600
        )
        if early_sellers > thresholds.early_sell_warning_count:
            indicators.append(
                f"Early profit taking: {early_sellers} buyers sold within 1 hour"
            )
        
        # Check for large unrealized profits
        large_unrealized = sum(
            1 for b in buyers
            if b.pnl_percentage > thresholds.significant_profit_multiplier * 100
        )
        if large_unrealized > len(buyers) * 0.3:
            indicators.append(
                f"Many large unrealized gains: {large_unrealized} buyers up >{thresholds.significant_profit_multiplier}x"
            )
        
        # Check concentration
        total_investment = sum(b.initial_investment for b in buyers)
        if total_investment > 0:
            top_buyer = max(buyers, key=lambda b: b.initial_investment)
            top_percentage = top_buyer.initial_investment / total_investment * 100
            if top_percentage > 50:
                indicators.append(
                    f"High concentration: top buyer has {top_percentage:.1f}% of early positions"
                )
        
        return indicators
    
    async def record_sell(
        self,
        token_address: str,
        buyer_address: str,
        sell_amount: float,
        sell_price: float,
        timestamp: int
    ):
        """Record a sell transaction from an early buyer"""
        
        async with self._lock:
            buyers = self._early_buyers.get(token_address, [])
            
            for buyer in buyers:
                if buyer.address == buyer_address:
                    # Calculate realized PnL
                    if buyer.token_amount > 0:
                        sell_ratio = min(1, sell_amount / buyer.token_amount)
                        buyer.sell_percentage = min(100, buyer.sell_percentage + sell_ratio * 100)
                        
                        if buyer.sell_percentage >= 100:
                            buyer.has_sold = True
                        
                        # Calculate realized PnL
                        cost_basis = buyer.initial_investment * sell_ratio
                        sale_value = sell_amount * sell_price
                        pnl = sale_value - cost_basis
                        buyer.realized_pnl += pnl
                    
                    buyer.last_update = timestamp
                    break
    
    async def get_buyer_details(
        self,
        token_address: str,
        buyer_address: str
    ) -> Optional[Dict[str, Any]]:
        """Get details for a specific early buyer"""
        
        async with self._lock:
            buyers = self._early_buyers.get(token_address, [])
            
            for buyer in buyers:
                if buyer.address == buyer_address:
                    return {
                        'address': shorten_address(buyer.address),
                        'position_rank': buyer.position_rank,
                        'entry_price': buyer.entry_price,
                        'entry_time': buyer.entry_timestamp,
                        'initial_investment': format_currency(buyer.initial_investment),
                        'token_amount': buyer.token_amount,
                        'unrealized_pnl': format_currency(buyer.unrealized_pnl),
                        'realized_pnl': format_currency(buyer.realized_pnl),
                        'pnl_percentage': round(buyer.pnl_percentage, 2),
                        'has_sold': buyer.has_sold,
                        'sell_percentage': round(buyer.sell_percentage, 2),
                        'status': self._classify_buyer_status(buyer)
                    }
        
        return None
    
    def _classify_buyer_status(self, buyer: EarlyBuyer) -> str:
        """Classify buyer status"""
        if buyer.has_sold:
            if buyer.realized_pnl > 0:
                return "profit_taker"
            else:
                return "stopped_out"
        elif buyer.pnl_percentage > 100:
            return "diamond_hands"
        elif buyer.pnl_percentage > 0:
            return "in_profit"
        else:
            return "holding"
    
    async def get_top_performers(
        self,
        token_address: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top performing early buyers"""
        
        async with self._lock:
            buyers = self._early_buyers.get(token_address, [])
        
        # Sort by PnL percentage
        sorted_buyers = sorted(
            buyers,
            key=lambda b: b.pnl_percentage,
            reverse=True
        )
        
        return [
            {
                'rank': i + 1,
                'address': shorten_address(b.address),
                'pnl_percentage': round(b.pnl_percentage, 2),
                'unrealized_pnl': format_currency(b.unrealized_pnl),
                'status': self._classify_buyer_status(b)
            }
            for i, b in enumerate(sorted_buyers[:limit])
        ]
    
    async def cleanup_old_data(self):
        """Clean up data for old tokens"""
        
        cutoff = get_timestamp() - (7 * 86400)  # 7 days
        
        async with self._lock:
            old_tokens = [
                addr for addr, buyers in self._early_buyers.items()
                if buyers and all(b.last_update < cutoff for b in buyers)
            ]
            
            for token in old_tokens:
                del self._early_buyers[token]
                if token in self._tracked_tokens:
                    del self._tracked_tokens[token]
            
            if old_tokens:
                logger.info(f"Cleaned up {len(old_tokens)} old token tracking data")


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_early_buyer_tracker: Optional[EarlyBuyerTracker] = None


def get_early_buyer_tracker() -> EarlyBuyerTracker:
    """Get or create early buyer tracker singleton"""
    global _early_buyer_tracker
    if _early_buyer_tracker is None:
        _early_buyer_tracker = EarlyBuyerTracker()
    return _early_buyer_tracker
