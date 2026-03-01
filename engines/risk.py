# ============================================================
# RISK SCORING ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from config.settings import get_config
from utils.logger import get_logger
from api.dexscreener import TokenPair


logger = get_logger("risk_engine")


class RiskLevel(Enum):
    """Risk level classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskScore:
    """Risk score result"""
    total_score: float  # 0-100
    level: RiskLevel
    components: Dict[str, float]
    factors: List[str]
    recommendations: List[str]


class RiskScoringEngine:
    """Calculate comprehensive risk scores for tokens"""
    
    def __init__(self):
        self.config = get_config()
        self.risk_config = self.config.strategy.risk_scoring
        self.weights = self.risk_config.weights
        self.thresholds = self.risk_config.thresholds
        self._cache: Dict[str, RiskScore] = {}
        self._lock = asyncio.Lock()
    
    async def calculate_risk_score(
        self,
        pair: TokenPair,
        additional_data: Optional[Dict] = None
    ) -> RiskScore:
        """Calculate comprehensive risk score for a token pair"""
        cache_key = f"{pair.token_address}_{get_timestamp() // 60}"  # Cache for 1 minute
        
        async with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
        
        components = {}
        factors = []
        recommendations = []
        
        # Calculate individual risk components
        components['liquidity_risk'] = await self._calculate_liquidity_risk(pair)
        components['volume_risk'] = await self._calculate_volume_risk(pair)
        components['holder_concentration'] = await self._calculate_holder_risk(pair, additional_data)
        components['contract_risk'] = await self._calculate_contract_risk(pair, additional_data)
        components['developer_risk'] = await self._calculate_developer_risk(additional_data)
        
        # Apply weights
        total_score = sum(
            components[key] * getattr(self.weights, key, 0)
            for key in components
        )
        
        # Determine risk level
        level = self._determine_risk_level(total_score)
        
        # Generate factors and recommendations
        factors, recommendations = self._generate_analysis(components, pair)
        
        risk_score = RiskScore(
            total_score=round(total_score, 2),
            level=level,
            components=components,
            factors=factors,
            recommendations=recommendations
        )
        
        # Cache result
        async with self._lock:
            self._cache[cache_key] = risk_score
            # Cleanup old cache entries
            if len(self._cache) > 1000:
                self._cache.clear()
        
        return risk_score
    
    async def _calculate_liquidity_risk(self, pair: TokenPair) -> float:
        """Calculate liquidity-related risk (0-100, higher = more risky)"""
        risk = 0.0
        
        # Low liquidity is risky
        if pair.liquidity_usd < 10000:
            risk += 50
        elif pair.liquidity_usd < 50000:
            risk += 30
        elif pair.liquidity_usd < 100000:
            risk += 15
        
        # Liquidity to market cap ratio
        if pair.market_cap > 0:
            liq_ratio = pair.liquidity_usd / pair.market_cap
            if liq_ratio < 0.1:
                risk += 25
            elif liq_ratio < 0.2:
                risk += 10
        
        # Price impact risk for $1000 trade
        if pair.liquidity_usd > 0:
            price_impact = (1000 / pair.liquidity_usd) * 100
            if price_impact > 5:
                risk += 20
            elif price_impact > 2:
                risk += 10
        
        return min(100, risk)
    
    async def _calculate_volume_risk(self, pair: TokenPair) -> float:
        """Calculate volume-related risk"""
        risk = 0.0
        
        # Low volume is risky
        if pair.volume_24h < 5000:
            risk += 40
        elif pair.volume_24h < 20000:
            risk += 20
        
        # Volume to liquidity ratio (velocity)
        if pair.liquidity_usd > 0:
            velocity = pair.volume_24h / pair.liquidity_usd
            if velocity > 10:  # Unusually high velocity
                risk += 20
            elif velocity < 0.1:  # Very low velocity
                risk += 15
        
        # Volume consistency check
        if pair.volume_24h > 0 and pair.volume_1h > 0:
            hourly_avg = pair.volume_24h / 24
            if pair.volume_1h > hourly_avg * 5:  # Spike in volume
                risk += 10
        
        # Buy/sell ratio risk
        if pair.buy_ratio < 0.4:
            risk += 15
        
        return min(100, risk)
    
    async def _calculate_holder_risk(
        self,
        pair: TokenPair,
        additional_data: Optional[Dict]
    ) -> float:
        """Calculate holder concentration risk"""
        risk = 0.0
        
        # Estimate holders from transaction data
        holder_estimate = pair.holder_estimate
        
        if holder_estimate < 50:
            risk += 40
        elif holder_estimate < 100:
            risk += 25
        elif holder_estimate < 500:
            risk += 10
        
        # Check for whale concentration if available
        if additional_data:
            top_holders = additional_data.get('top_holders', [])
            if top_holders:
                top_10_percent = sum(h.get('percentage', 0) for h in top_holders[:10])
                if top_10_percent > 50:
                    risk += 30
                elif top_10_percent > 30:
                    risk += 15
        
        return min(100, risk)
    
    async def _calculate_contract_risk(
        self,
        pair: TokenPair,
        additional_data: Optional[Dict]
    ) -> float:
        """Calculate smart contract risk"""
        risk = 0.0
        
        if not additional_data:
            return 50  # Unknown contract = medium risk
        
        contract_info = additional_data.get('contract_info', {})
        
        # Unverified contract
        if not contract_info.get('verified', False):
            risk += 30
        
        # Dangerous functions
        dangerous_functions = [
            'mint', 'burn', 'pause', 'blacklist',
            'setTax', 'renounceOwnership', 'transferOwnership'
        ]
        
        functions = contract_info.get('functions', [])
        for func in dangerous_functions:
            if func in functions:
                risk += 10
        
        # Proxy contract
        if contract_info.get('is_proxy', False):
            risk += 15
        
        # Token age
        if pair.pair_created_at:
            age_hours = (get_timestamp() - pair.pair_created_at) / 3600
            if age_hours < 1:
                risk += 20
            elif age_hours < 6:
                risk += 10
        
        return min(100, risk)
    
    async def _calculate_developer_risk(
        self,
        additional_data: Optional[Dict]
    ) -> float:
        """Calculate developer-related risk"""
        risk = 0.0
        
        if not additional_data:
            return 50  # Unknown developer = medium risk
        
        dev_info = additional_data.get('developer', {})
        
        # Previous rug pulls
        rug_count = dev_info.get('previous_rugs', 0)
        if rug_count > 0:
            risk += min(50, rug_count * 25)
        
        # Liquidity lock
        if not dev_info.get('liquidity_locked', False):
            risk += 20
        else:
            lock_time = dev_info.get('lock_time_days', 0)
            if lock_time < 30:
                risk += 10
        
        # Developer wallet activity
        dev_wallet = dev_info.get('wallet', {})
        if dev_wallet.get('recent_large_transfers', False):
            risk += 15
        
        # Social presence
        if not dev_info.get('social_verified', False):
            risk += 10
        
        return min(100, risk)
    
    def _determine_risk_level(self, score: float) -> RiskLevel:
        """Determine risk level from score"""
        if score <= self.thresholds.low_risk_max:
            return RiskLevel.LOW
        elif score <= self.thresholds.medium_risk_max:
            return RiskLevel.MEDIUM
        elif score <= self.thresholds.high_risk_max:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
    
    def _generate_analysis(
        self,
        components: Dict[str, float],
        pair: TokenPair
    ) -> tuple:
        """Generate risk factors and recommendations"""
        factors = []
        recommendations = []
        
        # Liquidity analysis
        if components['liquidity_risk'] > 50:
            factors.append("Very low liquidity - high slippage risk")
            recommendations.append("Avoid large positions")
        elif components['liquidity_risk'] > 30:
            factors.append("Low liquidity")
            recommendations.append("Use smaller position sizes")
        
        # Volume analysis
        if components['volume_risk'] > 40:
            factors.append("Low trading volume - exit risk")
            recommendations.append("Be prepared for difficulty exiting")
        
        # Holder analysis
        if components['holder_concentration'] > 50:
            factors.append("High holder concentration - whale manipulation risk")
            recommendations.append("Monitor whale wallets closely")
        
        # Contract analysis
        if components['contract_risk'] > 50:
            factors.append("Contract has risk factors")
            recommendations.append("Review contract before investing")
        
        # Developer analysis
        if components['developer_risk'] > 50:
            factors.append("Developer has risk factors")
            recommendations.append("Research developer history")
        
        return factors, recommendations
    
    async def get_risk_trend(
        self,
        token_address: str,
        history: List[Dict]
    ) -> Dict[str, Any]:
        """Analyze risk score trend over time"""
        if len(history) < 2:
            return {"trend": "insufficient_data", "change": 0}
        
        scores = [h.get('risk_score', 0) for h in history]
        recent_avg = sum(scores[-5:]) / len(scores[-5:])
        older_avg = sum(scores[:-5]) / max(1, len(scores[:-5]))
        
        change = recent_avg - older_avg
        
        if change > 15:
            trend = "rapidly_increasing"
        elif change > 5:
            trend = "increasing"
        elif change < -15:
            trend = "rapidly_decreasing"
        elif change < -5:
            trend = "decreasing"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "change": round(change, 2),
            "current": scores[-1] if scores else 0,
            "average": round(sum(scores) / len(scores), 2)
        }


# Utility function for timestamp
from utils.helpers import get_timestamp


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_risk_engine: Optional[RiskScoringEngine] = None


def get_risk_engine() -> RiskScoringEngine:
    """Get or create risk engine singleton"""
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskScoringEngine()
    return _risk_engine
