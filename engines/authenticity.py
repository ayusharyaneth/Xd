# ============================================================
# VOLUME AUTHENTICITY ENGINE
# ============================================================

import asyncio
import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict
import statistics

from config.settings import get_config
from utils.logger import get_logger
from api.dexscreener import TokenPair


logger = get_logger("authenticity_engine")


@dataclass
class AuthenticityScore:
    """Volume authenticity score result"""
    score: float  # 0-100, higher = more authentic
    natural_volume_ratio: float
    wash_trade_score: float
    suspicious_patterns: List[str]
    metrics: Dict[str, float]
    confidence: float  # 0-1


class VolumeAuthenticityEngine:
    """Detect volume manipulation and wash trading"""
    
    def __init__(self):
        self.config = get_config()
        self.auth_config = self.config.strategy.volume_authenticity
        self._transaction_history: Dict[str, List[Dict]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def analyze_volume(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]] = None
    ) -> AuthenticityScore:
        """Analyze volume authenticity for a token pair"""
        
        metrics = {}
        suspicious_patterns = []
        
        # Statistical analysis
        metrics['trade_variance'] = await self._calculate_trade_variance(
            pair, transaction_data
        )
        metrics['time_distribution'] = await self._analyze_time_distribution(
            pair, transaction_data
        )
        metrics['buyer_seller_overlap'] = await self._calculate_overlap(
            pair, transaction_data
        )
        
        # Pattern detection
        patterns = await self._detect_patterns(pair, transaction_data)
        suspicious_patterns.extend(patterns)
        
        # Calculate wash trade score
        wash_score = self._calculate_wash_score(metrics, suspicious_patterns)
        
        # Calculate natural volume ratio
        natural_ratio = max(0, 1 - wash_score)
        
        # Calculate final authenticity score
        authenticity = self._calculate_authenticity_score(
            metrics, wash_score, suspicious_patterns
        )
        
        # Calculate confidence based on data availability
        confidence = self._calculate_confidence(pair, transaction_data)
        
        return AuthenticityScore(
            score=round(authenticity, 2),
            natural_volume_ratio=round(natural_ratio, 2),
            wash_trade_score=round(wash_score, 2),
            suspicious_patterns=suspicious_patterns,
            metrics=metrics,
            confidence=round(confidence, 2)
        )
    
    async def _calculate_trade_variance(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]]
    ) -> float:
        """Calculate trade size variance (high variance = suspicious)"""
        if not transaction_data:
            # Estimate from available data
            if pair.txns_24h_buy + pair.txns_24h_sell == 0:
                return 0.5
            avg_trade = pair.volume_24h / (pair.txns_24h_buy + pair.txns_24h_sell)
            # Assume high variance if we don't have detailed data
            return 0.6 if avg_trade > 1000 else 0.4
        
        trade_sizes = [tx.get('amount_usd', 0) for tx in transaction_data]
        if len(trade_sizes) < 2:
            return 0.5
        
        try:
            mean_size = statistics.mean(trade_sizes)
            if mean_size == 0:
                return 0.5
            
            variance = statistics.variance(trade_sizes)
            cv = math.sqrt(variance) / mean_size  # Coefficient of variation
            
            # Normalize to 0-1 scale
            return min(1.0, cv / 3.0)
        except:
            return 0.5
    
    async def _analyze_time_distribution(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]]
    ) -> float:
        """Analyze transaction time distribution (uniform = natural)"""
        if not transaction_data or len(transaction_data) < 10:
            # Use transaction count as proxy
            if pair.txns_24h_buy + pair.txns_24h_sell < 50:
                return 0.5  # Insufficient data
            
            # Higher transaction count suggests more natural distribution
            tx_count = pair.txns_24h_buy + pair.txns_24h_sell
            return min(1.0, tx_count / 500)
        
        timestamps = [tx.get('timestamp', 0) for tx in transaction_data]
        timestamps.sort()
        
        if len(timestamps) < 2:
            return 0.5
        
        # Calculate intervals between transactions
        intervals = [
            timestamps[i] - timestamps[i-1]
            for i in range(1, len(timestamps))
        ]
        
        if not intervals:
            return 0.5
        
        # Check for clustering (many transactions at same time)
        zero_intervals = sum(1 for i in intervals if i < 2)
        clustering_ratio = zero_intervals / len(intervals)
        
        # High clustering suggests bot activity
        return max(0, 1 - clustering_ratio * 2)
    
    async def _calculate_overlap(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]]
    ) -> float:
        """Calculate buyer-seller overlap (high overlap = wash trading)"""
        if not transaction_data:
            # Estimate from buy/sell ratio
            if pair.txns_24h_buy == 0 or pair.txns_24h_sell == 0:
                return 0.0
            
            # Similar buy/sell counts might indicate wash trading
            ratio = min(pair.txns_24h_buy, pair.txns_24h_sell) / max(pair.txns_24h_buy, pair.txns_24h_sell)
            return 1 - ratio
        
        buyers = set()
        sellers = set()
        
        for tx in transaction_data:
            if tx.get('type') == 'buy':
                buyers.add(tx.get('buyer', ''))
            elif tx.get('type') == 'sell':
                sellers.add(tx.get('seller', ''))
        
        if not buyers or not sellers:
            return 0.0
        
        overlap = buyers & sellers
        total_unique = buyers | sellers
        
        if not total_unique:
            return 0.0
        
        return len(overlap) / len(total_unique)
    
    async def _detect_patterns(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]]
    ) -> List[str]:
        """Detect suspicious trading patterns"""
        patterns = []
        
        if not transaction_data:
            # Use available metrics to infer patterns
            if pair.txns_5m_buy > 0 and pair.txns_5m_sell > 0:
                buy_sell_ratio = pair.txns_5m_buy / (pair.txns_5m_buy + pair.txns_5m_sell)
                if 0.45 < buy_sell_ratio < 0.55:
                    patterns.append("balanced_buy_sell")
            
            return patterns
        
        # Check for circular trading
        if await self._detect_circular_trading(transaction_data):
            patterns.append("circular_trading")
        
        # Check for matched orders
        if await self._detect_matched_orders(transaction_data):
            patterns.append("matched_orders")
        
        # Check for timestamp clustering
        if await self._detect_timestamp_clustering(transaction_data):
            patterns.append("timestamp_clustering")
        
        # Check for trade size patterns
        if await self._detect_size_patterns(transaction_data):
            patterns.append("suspicious_size_pattern")
        
        return patterns
    
    async def _detect_circular_trading(
        self,
        transaction_data: List[Dict]
    ) -> bool:
        """Detect circular trading patterns"""
        # Look for A -> B -> A patterns
        wallet_flows = defaultdict(set)
        
        for tx in transaction_data:
            buyer = tx.get('buyer', '')
            seller = tx.get('seller', '')
            if buyer and seller:
                wallet_flows[seller].add(buyer)
        
        # Check for cycles
        for wallet, destinations in wallet_flows.items():
            for dest in destinations:
                if wallet in wallet_flows.get(dest, set()):
                    return True
        
        return False
    
    async def _detect_matched_orders(
        self,
        transaction_data: List[Dict]
    ) -> bool:
        """Detect matched buy/sell orders"""
        # Group by timestamp (within 5 seconds)
        time_groups = defaultdict(list)
        for tx in transaction_data:
            ts = tx.get('timestamp', 0)
            time_groups[ts // 5].append(tx)
        
        # Check for matched amounts in same time window
        for group in time_groups.values():
            if len(group) < 2:
                continue
            
            buys = [tx for tx in group if tx.get('type') == 'buy']
            sells = [tx for tx in group if tx.get('type') == 'sell']
            
            for buy in buys:
                buy_amount = buy.get('amount', 0)
                for sell in sells:
                    sell_amount = sell.get('amount', 0)
                    # If amounts are very similar, might be matched
                    if abs(buy_amount - sell_amount) / max(buy_amount, sell_amount) < 0.01:
                        return True
        
        return False
    
    async def _detect_timestamp_clustering(
        self,
        transaction_data: List[Dict]
    ) -> bool:
        """Detect unusual timestamp clustering"""
        timestamps = [tx.get('timestamp', 0) for tx in transaction_data]
        if len(timestamps) < 10:
            return False
        
        # Count transactions per second
        second_counts = defaultdict(int)
        for ts in timestamps:
            second_counts[ts] += 1
        
        # Check for high clustering
        max_in_second = max(second_counts.values())
        avg_per_second = len(timestamps) / len(second_counts)
        
        if max_in_second > avg_per_second * 5 and max_in_second > 5:
            return True
        
        return False
    
    async def _detect_size_patterns(
        self,
        transaction_data: List[Dict]
    ) -> bool:
        """Detect suspicious trade size patterns"""
        sizes = [tx.get('amount_usd', 0) for tx in transaction_data]
        if len(sizes) < 10:
            return False
        
        # Check for repeated sizes (bot behavior)
        size_counts = defaultdict(int)
        for size in sizes:
            # Round to nearest 10 for grouping
            rounded = round(size, -1)
            size_counts[rounded] += 1
        
        # If any size appears too frequently
        max_count = max(size_counts.values())
        if max_count > len(sizes) * 0.2:  # More than 20% same size
            return True
        
        return False
    
    def _calculate_wash_score(
        self,
        metrics: Dict[str, float],
        patterns: List[str]
    ) -> float:
        """Calculate wash trading probability score"""
        score = 0.0
        
        # Trade variance contribution
        score += metrics.get('trade_variance', 0) * 0.25
        
        # Time distribution contribution
        score += (1 - metrics.get('time_distribution', 0.5)) * 0.25
        
        # Buyer-seller overlap contribution
        score += metrics.get('buyer_seller_overlap', 0) * 0.30
        
        # Pattern detection contribution
        pattern_score = min(1.0, len(patterns) * 0.2)
        score += pattern_score * 0.20
        
        return min(1.0, score)
    
    def _calculate_authenticity_score(
        self,
        metrics: Dict[str, float],
        wash_score: float,
        patterns: List[str]
    ) -> float:
        """Calculate final authenticity score (0-100)"""
        # Base score from wash trading
        base_score = (1 - wash_score) * 100
        
        # Adjust based on metrics
        if metrics.get('trade_variance', 0.5) > 0.8:
            base_score -= 10
        
        if metrics.get('time_distribution', 0.5) < 0.3:
            base_score -= 15
        
        if metrics.get('buyer_seller_overlap', 0) > 0.5:
            base_score -= 20
        
        # Penalty for each suspicious pattern
        base_score -= len(patterns) * 5
        
        return max(0, min(100, base_score))
    
    def _calculate_confidence(
        self,
        pair: TokenPair,
        transaction_data: Optional[List[Dict]]
    ) -> float:
        """Calculate confidence level in the analysis"""
        confidence = 0.5  # Base confidence
        
        # More transaction data = higher confidence
        if transaction_data:
            if len(transaction_data) > 100:
                confidence += 0.3
            elif len(transaction_data) > 50:
                confidence += 0.2
            elif len(transaction_data) > 20:
                confidence += 0.1
        
        # Higher volume = more data to analyze
        if pair.volume_24h > 100000:
            confidence += 0.1
        elif pair.volume_24h > 50000:
            confidence += 0.05
        
        # More transactions = better analysis
        total_txns = pair.txns_24h_buy + pair.txns_24h_sell
        if total_txns > 500:
            confidence += 0.1
        elif total_txns > 200:
            confidence += 0.05
        
        return min(1.0, confidence)
    
    async def get_volume_breakdown(
        self,
        pair: TokenPair,
        transaction_data: List[Dict]
    ) -> Dict[str, Any]:
        """Get detailed volume breakdown"""
        if not transaction_data:
            return {
                'natural_volume': pair.volume_24h * 0.7,  # Estimate
                'suspicious_volume': pair.volume_24h * 0.3,
                'confidence': 0.3
            }
        
        total_volume = sum(tx.get('amount_usd', 0) for tx in transaction_data)
        
        # Classify each transaction
        natural_volume = 0
        suspicious_volume = 0
        
        for tx in transaction_data:
            amount = tx.get('amount_usd', 0)
            
            # Simple heuristics for classification
            is_suspicious = (
                tx.get('is_wash', False) or
                tx.get('timestamp_cluster', False) or
                tx.get('size_pattern', False)
            )
            
            if is_suspicious:
                suspicious_volume += amount
            else:
                natural_volume += amount
        
        return {
            'natural_volume': round(natural_volume, 2),
            'suspicious_volume': round(suspicious_volume, 2),
            'natural_percentage': round(natural_volume / total_volume * 100, 2) if total_volume > 0 else 0,
            'confidence': min(1.0, len(transaction_data) / 200)
        }


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_authenticity_engine: Optional[VolumeAuthenticityEngine] = None


def get_authenticity_engine() -> VolumeAuthenticityEngine:
    """Get or create authenticity engine singleton"""
    global _authenticity_engine
    if _authenticity_engine is None:
        _authenticity_engine = VolumeAuthenticityEngine()
    return _authenticity_engine
