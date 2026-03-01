# ============================================================
# BUY QUALITY SCORING ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import defaultdict
import statistics

from config.settings import get_config
from utils.logger import get_logger
from api.dexscreener import TokenPair


logger = get_logger("buy_quality_engine")


@dataclass
class BuyQualityScore:
    """Buy quality score result"""
    score: float  # 0-100
    tier_breakdown: Dict[str, Dict[str, Any]]
    quality_factors: Dict[str, float]
    wallet_diversity_score: float
    pressure_sustainability: float
    entry_timing_score: float
    holding_pattern_score: float
    analysis: List[str]


@dataclass
class WalletTier:
    """Wallet tier classification"""
    name: str
    min_usd: float
    weight: float
    description: str


class BuyQualityEngine:
    """Analyze quality of buying activity"""
    
    def __init__(self):
        self.config = get_config()
        self.quality_config = self.config.strategy.buy_quality
        self._tier_cache: Dict[str, str] = {}
        self._buy_history: Dict[str, List[Dict]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    def _get_wallet_tiers(self) -> Dict[str, WalletTier]:
        """Get wallet tier definitions"""
        tiers = {}
        for name, config in self.quality_config.wallet_tiers.items():
            tiers[name] = WalletTier(
                name=name,
                min_usd=config.min_usd,
                weight=config.weight,
                description=self._get_tier_description(name)
            )
        return tiers
    
    def _get_tier_description(self, tier_name: str) -> str:
        """Get description for wallet tier"""
        descriptions = {
            'whale': "Large institutional/smart money",
            'shark': "Experienced large traders",
            'dolphin': "Active medium traders",
            'fish': "Regular retail traders",
            'shrimp': "Small/new traders"
        }
        return descriptions.get(tier_name, "Unknown tier")
    
    async def analyze_buy_quality(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]] = None,
        wallet_data: Optional[List[Dict]] = None
    ) -> BuyQualityScore:
        """Analyze buy quality for a token pair"""
        
        tiers = self._get_wallet_tiers()
        
        # Analyze tier breakdown
        tier_breakdown = await self._analyze_tiers(
            pair, transaction_data, wallet_data, tiers
        )
        
        # Calculate quality factors
        wallet_diversity = await self._calculate_wallet_diversity(
            pair, transaction_data
        )
        
        pressure_sustainability = await self._calculate_sustainability(
            pair, transaction_data
        )
        
        entry_timing = await self._calculate_entry_timing(
            pair, transaction_data
        )
        
        holding_pattern = await self._calculate_holding_pattern(
            pair, wallet_data
        )
        
        # Calculate weighted score
        factors = self.quality_config.quality_factors
        score = (
            wallet_diversity * factors.get('wallet_diversity', 0.25) +
            pressure_sustainability * factors.get('buy_pressure_sustainability', 0.30) +
            entry_timing * factors.get('entry_timing_quality', 0.25) +
            holding_pattern * factors.get('holding_pattern', 0.20)
        ) * 100
        
        # Generate analysis
        analysis = self._generate_analysis(
            tier_breakdown,
            wallet_diversity,
            pressure_sustainability,
            entry_timing,
            holding_pattern
        )
        
        return BuyQualityScore(
            score=round(score, 2),
            tier_breakdown=tier_breakdown,
            quality_factors={
                'wallet_diversity': round(wallet_diversity, 2),
                'pressure_sustainability': round(pressure_sustainability, 2),
                'entry_timing': round(entry_timing, 2),
                'holding_pattern': round(holding_pattern, 2)
            },
            wallet_diversity_score=round(wallet_diversity * 100, 2),
            pressure_sustainability=round(pressure_sustainability * 100, 2),
            entry_timing_score=round(entry_timing * 100, 2),
            holding_pattern_score=round(holding_pattern * 100, 2),
            analysis=analysis
        )
    
    async def _analyze_tiers(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]],
        wallet_data: Optional[List[Dict]],
        tiers: Dict[str, WalletTier]
    ) -> Dict[str, Dict[str, Any]]:
        """Analyze wallet tier breakdown"""
        
        breakdown = {}
        
        if not transaction_data and not wallet_data:
            # Estimate from available data
            # Use volume and transaction count to estimate
            if pair.txns_24h_buy > 0:
                avg_buy = pair.volume_24h * pair.buy_ratio / pair.txns_24h_buy
                
                # Estimate distribution
                breakdown['estimated'] = {
                    'average_buy_size': round(avg_buy, 2),
                    'total_buys': pair.txns_24h_buy,
                    'note': 'Estimated from aggregate data'
                }
            
            return breakdown
        
        # Count buys by tier
        tier_counts = defaultdict(lambda: {'count': 0, 'volume': 0})
        
        # Process transaction data
        if transaction_data:
            for tx in transaction_data:
                if tx.get('type') != 'buy':
                    continue
                
                amount = tx.get('amount_usd', 0)
                tier_name = self._classify_amount(amount, tiers)
                
                tier_counts[tier_name]['count'] += 1
                tier_counts[tier_name]['volume'] += amount
        
        # Process wallet data
        if wallet_data:
            for wallet in wallet_data:
                avg_buy = wallet.get('avg_buy_size', 0)
                tier_name = self._classify_amount(avg_buy, tiers)
                
                tier_counts[tier_name]['count'] += 1
                tier_counts[tier_name]['volume'] += wallet.get('total_bought', 0)
        
        # Calculate breakdown
        total_count = sum(t['count'] for t in tier_counts.values())
        total_volume = sum(t['volume'] for t in tier_counts.values())
        
        for tier_name, tier_info in tiers.items():
            count = tier_counts[tier_name]['count']
            volume = tier_counts[tier_name]['volume']
            
            breakdown[tier_name] = {
                'count': count,
                'percentage': round(count / total_count * 100, 2) if total_count > 0 else 0,
                'volume': round(volume, 2),
                'volume_percentage': round(volume / total_volume * 100, 2) if total_volume > 0 else 0,
                'weight': tier_info.weight,
                'description': tier_info.description
            }
        
        return breakdown
    
    def _classify_amount(self, amount: float, tiers: Dict[str, WalletTier]) -> str:
        """Classify buy amount into tier"""
        sorted_tiers = sorted(
            tiers.items(),
            key=lambda x: x[1].min_usd,
            reverse=True
        )
        
        for tier_name, tier in sorted_tiers:
            if amount >= tier.min_usd:
                return tier_name
        
        return 'shrimp'
    
    async def _calculate_wallet_diversity(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]]
    ) -> float:
        """Calculate wallet diversity score (0-1)"""
        
        if not transaction_data:
            # Estimate from transaction count
            unique_estimate = min(pair.txns_24h_buy, pair.holder_estimate)
            if unique_estimate == 0:
                return 0.5
            
            # Higher diversity = better
            diversity_ratio = unique_estimate / max(1, pair.txns_24h_buy)
            return min(1.0, diversity_ratio)
        
        # Count unique buyers
        buyers = set()
        for tx in transaction_data:
            if tx.get('type') == 'buy':
                buyers.add(tx.get('buyer', ''))
        
        unique_buyers = len(buyers)
        total_buys = sum(1 for tx in transaction_data if tx.get('type') == 'buy')
        
        if total_buys == 0:
            return 0.5
        
        diversity_ratio = unique_buyers / total_buys
        
        # Penalize if too concentrated
        if diversity_ratio < 0.3:
            return diversity_ratio * 0.5
        
        return min(1.0, diversity_ratio)
    
    async def _calculate_sustainability(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]]
    ) -> float:
        """Calculate buy pressure sustainability (0-1)"""
        
        if not transaction_data or len(transaction_data) < 10:
            # Use price and volume trends as proxy
            if pair.price_change_5m > 0 and pair.volume_24h > 0:
                # Positive momentum with volume suggests sustainability
                sustainability = min(1.0, pair.price_change_5m / 50)
                return max(0.3, sustainability)
            return 0.5
        
        # Analyze buy pressure over time
        buy_counts = defaultdict(int)
        for tx in transaction_data:
            if tx.get('type') == 'buy':
                hour = tx.get('timestamp', 0) // 3600
                buy_counts[hour] += 1
        
        if len(buy_counts) < 2:
            return 0.5
        
        # Calculate trend
        hours = sorted(buy_counts.keys())
        counts = [buy_counts[h] for h in hours]
        
        # Check if buy pressure is increasing or stable
        if len(counts) >= 3:
            recent_avg = sum(counts[-3:]) / 3
            older_avg = sum(counts[:-3]) / max(1, len(counts) - 3)
            
            if recent_avg >= older_avg * 0.8:  # Not declining more than 20%
                return min(1.0, recent_avg / max(1, older_avg))
        
        return 0.5
    
    async def _calculate_entry_timing(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]]
    ) -> float:
        """Calculate entry timing quality (0-1)"""
        
        # Early entry is better
        if pair.pair_created_at:
            age_hours = (get_timestamp() - pair.pair_created_at) / 3600
            
            # Very early entry (first hour) - highest quality
            if age_hours < 1:
                return 1.0
            elif age_hours < 6:
                return 0.9
            elif age_hours < 24:
                return 0.8
            elif age_hours < 72:
                return 0.6
            else:
                return 0.4
        
        # Check if buyers are entering on dips
        if transaction_data:
            dip_buys = 0
            total_buys = 0
            
            for tx in transaction_data:
                if tx.get('type') == 'buy':
                    total_buys += 1
                    if tx.get('price_change_5m', 0) < 0:
                        dip_buys += 1
            
            if total_buys > 0:
                dip_ratio = dip_buys / total_buys
                return 0.5 + (dip_ratio * 0.5)  # Bonus for buying dips
        
        return 0.5
    
    async def _calculate_holding_pattern(
        self,
        pair: TokenPair,
        wallet_data: Optional[List[Dict]]
    ) -> float:
        """Calculate holding pattern score (0-1)"""
        
        if not wallet_data:
            # Estimate from sell pressure
            if pair.txns_24h_sell == 0:
                return 1.0  # No sells = strong holding
            
            sell_ratio = pair.txns_24h_sell / max(1, pair.txns_24h_buy + pair.txns_24h_sell)
            return max(0, 1 - sell_ratio * 2)
        
        # Analyze holding times
        holding_scores = []
        
        for wallet in wallet_data:
            avg_hold_time = wallet.get('avg_hold_time_hours', 0)
            sell_ratio = wallet.get('sell_ratio', 0)
            
            # Longer hold time = better
            if avg_hold_time > 48:
                hold_score = 1.0
            elif avg_hold_time > 24:
                hold_score = 0.8
            elif avg_hold_time > 6:
                hold_score = 0.6
            else:
                hold_score = 0.4
            
            # Lower sell ratio = better
            sell_score = max(0, 1 - sell_ratio)
            
            # Combined score
            wallet_score = (hold_score * 0.6) + (sell_score * 0.4)
            holding_scores.append(wallet_score)
        
        if not holding_scores:
            return 0.5
        
        return sum(holding_scores) / len(holding_scores)
    
    def _generate_analysis(
        self,
        tier_breakdown: Dict,
        wallet_diversity: float,
        sustainability: float,
        entry_timing: float,
        holding_pattern: float
    ) -> List[str]:
        """Generate human-readable analysis"""
        analysis = []
        
        # Tier analysis
        whale_pct = tier_breakdown.get('whale', {}).get('percentage', 0)
        if whale_pct > 20:
            analysis.append(f"Strong whale participation ({whale_pct}%)")
        elif whale_pct < 5:
            analysis.append("Limited whale interest")
        
        # Diversity analysis
        if wallet_diversity > 0.7:
            analysis.append("High wallet diversity - good distribution")
        elif wallet_diversity < 0.3:
            analysis.append("Low wallet diversity - concentrated buying")
        
        # Sustainability analysis
        if sustainability > 0.7:
            analysis.append("Buy pressure is sustainable")
        elif sustainability < 0.4:
            analysis.append("Buy pressure declining")
        
        # Entry timing analysis
        if entry_timing > 0.8:
            analysis.append("Excellent entry timing - early buyers")
        elif entry_timing < 0.5:
            analysis.append("Late entry - consider risk")
        
        # Holding pattern analysis
        if holding_pattern > 0.7:
            analysis.append("Strong holding pattern")
        elif holding_pattern < 0.4:
            analysis.append("Weak holding - high sell pressure")
        
        return analysis
    
    async def track_buy(
        self,
        token_address: str,
        buyer: str,
        amount_usd: float,
        timestamp: int
    ):
        """Track a buy transaction"""
        async with self._lock:
            self._buy_history[token_address].append({
                'buyer': buyer,
                'amount_usd': amount_usd,
                'timestamp': timestamp
            })
    
    async def get_buyer_profile(
        self,
        buyer: str,
        token_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get profile of a specific buyer"""
        
        async with self._lock:
            if token_address:
                buys = [
                    b for b in self._buy_history.get(token_address, [])
                    if b['buyer'] == buyer
                ]
            else:
                buys = []
                for token_buys in self._buy_history.values():
                    buys.extend([b for b in token_buys if b['buyer'] == buyer])
        
        if not buys:
            return {'error': 'No data for buyer'}
        
        total_spent = sum(b['amount_usd'] for b in buys)
        avg_buy = total_spent / len(buys)
        
        # Classify tier
        tiers = self._get_wallet_tiers()
        tier = self._classify_amount(avg_buy, tiers)
        
        return {
            'buyer': buyer,
            'total_buys': len(buys),
            'total_spent': round(total_spent, 2),
            'average_buy': round(avg_buy, 2),
            'tier': tier,
            'tier_description': tiers[tier].description
        }


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_buy_quality_engine: Optional[BuyQualityEngine] = None


def get_buy_quality_engine() -> BuyQualityEngine:
    """Get or create buy quality engine singleton"""
    global _buy_quality_engine
    if _buy_quality_engine is None:
        _buy_quality_engine = BuyQualityEngine()
    return _buy_quality_engine
