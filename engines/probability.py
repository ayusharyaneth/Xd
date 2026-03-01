# ============================================================
# RUG PROBABILITY ESTIMATOR ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp
from api.dexscreener import TokenPair


logger = get_logger("probability_engine")


class WarningLevel(Enum):
    """Warning level for rug probability"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RugProbability:
    """Rug pull probability assessment"""
    probability: float  # 0-1
    probability_percent: float  # 0-100
    warning_level: WarningLevel
    risk_factors: List[str]
    early_warning_signs: List[str]
    recommended_action: str
    component_scores: Dict[str, float]
    confidence: float


class RugProbabilityEstimator:
    """Estimate probability of rug pull"""
    
    def __init__(self):
        self.config = get_config()
        self.prob_config = self.config.strategy.rug_probability
        self._probability_history: Dict[str, List[Dict]] = {}
        self._risk_indicators: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()
    
    async def calculate_probability(
        self,
        pair: TokenPair,
        risk_score: Optional[float] = None,
        volume_authenticity: Optional[float] = None,
        developer_reputation: Optional[float] = None,
        holder_data: Optional[List[Dict]] = None,
        contract_data: Optional[Dict] = None
    ) -> RugProbability:
        """Calculate rug pull probability"""
        
        indicators = self.prob_config.indicators
        component_scores = {}
        risk_factors = []
        early_warnings = []
        
        # 1. Liquidity removal risk
        liq_risk = await self._assess_liquidity_risk(pair, contract_data)
        component_scores['liquidity_risk'] = liq_risk
        if liq_risk > 0.5:
            risk_factors.append(f"High liquidity removal risk ({liq_risk:.0%})")
        
        # 2. Holder concentration risk
        holder_risk = await self._assess_holder_risk(pair, holder_data)
        component_scores['holder_concentration'] = holder_risk
        if holder_risk > 0.5:
            risk_factors.append(f"High holder concentration risk ({holder_risk:.0%})")
        
        # 3. Contract risk
        contract_risk = await self._assess_contract_risk(contract_data)
        component_scores['contract_risk'] = contract_risk
        if contract_risk > 0.5:
            risk_factors.append(f"Contract risk factors ({contract_risk:.0%})")
        
        # 4. Developer risk
        dev_risk = await self._assess_developer_risk(developer_reputation)
        component_scores['developer_risk'] = dev_risk
        if dev_risk > 0.5:
            risk_factors.append(f"Developer risk factors ({dev_risk:.0%})")
        
        # 5. Volume manipulation risk
        vol_risk = await self._assess_volume_risk(pair, volume_authenticity)
        component_scores['volume_risk'] = vol_risk
        if vol_risk > 0.5:
            risk_factors.append(f"Volume manipulation risk ({vol_risk:.0%})")
        
        # Calculate weighted probability
        probability = (
            liq_risk * indicators.liquidity_removal_risk +
            holder_risk * indicators.holder_concentration_risk +
            contract_risk * indicators.contract_risk +
            dev_risk * indicators.developer_risk +
            vol_risk * indicators.volume_manipulation_risk
        )
        
        # Check for early warning signs
        early_warnings = await self._check_early_warnings(
            pair, contract_data, holder_data
        )
        
        # Boost probability if early warnings present
        if early_warnings:
            probability = min(1.0, probability * 1.2)
        
        # Determine warning level
        warning_level = self._determine_warning_level(probability)
        
        # Get recommended action
        recommended_action = self._get_recommended_action(warning_level, probability)
        
        # Calculate confidence
        confidence = self._calculate_confidence(component_scores)
        
        rug_prob = RugProbability(
            probability=round(probability, 4),
            probability_percent=round(probability * 100, 2),
            warning_level=warning_level,
            risk_factors=risk_factors,
            early_warning_signs=early_warnings,
            recommended_action=recommended_action,
            component_scores={k: round(v, 4) for k, v in component_scores.items()},
            confidence=round(confidence, 2)
        )
        
        # Store in history
        await self._store_probability(pair.token_address, rug_prob)
        
        return rug_prob
    
    async def _assess_liquidity_risk(
        self,
        pair: TokenPair,
        contract_data: Optional[Dict]
    ) -> float:
        """Assess liquidity removal risk (0-1)"""
        
        risk = 0.0
        
        # Low liquidity is risky
        if pair.liquidity_usd < 10000:
            risk += 0.4
        elif pair.liquidity_usd < 50000:
            risk += 0.2
        
        # Check if liquidity is locked
        if contract_data:
            if not contract_data.get('liquidity_locked', False):
                risk += 0.3
            else:
                # Check lock duration
                lock_days = contract_data.get('lock_time_days', 0)
                if lock_days < 30:
                    risk += 0.2
                elif lock_days < 90:
                    risk += 0.1
        else:
            # Unknown liquidity status
            risk += 0.15
        
        # Liquidity to market cap ratio
        if pair.market_cap > 0:
            ratio = pair.liquidity_usd / pair.market_cap
            if ratio < 0.1:
                risk += 0.2
            elif ratio < 0.2:
                risk += 0.1
        
        return min(1.0, risk)
    
    async def _assess_holder_risk(
        self,
        pair: TokenPair,
        holder_data: Optional[List[Dict]]
    ) -> float:
        """Assess holder concentration risk"""
        
        risk = 0.0
        
        if holder_data:
            # Calculate concentration
            total_supply = sum(h.get('amount', 0) for h in holder_data)
            if total_supply > 0:
                # Top holder percentage
                top_holder = max(h.get('amount', 0) for h in holder_data)
                top_percentage = top_holder / total_supply
                
                if top_percentage > 0.5:
                    risk += 0.4
                elif top_percentage > 0.3:
                    risk += 0.25
                elif top_percentage > 0.2:
                    risk += 0.15
                
                # Top 5 holders
                sorted_holders = sorted(
                    holder_data,
                    key=lambda h: h.get('amount', 0),
                    reverse=True
                )
                top5_amount = sum(h.get('amount', 0) for h in sorted_holders[:5])
                top5_percentage = top5_amount / total_supply
                
                if top5_percentage > 0.7:
                    risk += 0.3
                elif top5_percentage > 0.5:
                    risk += 0.15
        else:
            # Estimate from available data
            if pair.holder_estimate < 50:
                risk += 0.3
            elif pair.holder_estimate < 100:
                risk += 0.15
        
        return min(1.0, risk)
    
    async def _assess_contract_risk(
        self,
        contract_data: Optional[Dict]
    ) -> float:
        """Assess smart contract risk"""
        
        risk = 0.0
        
        if not contract_data:
            return 0.5  # Unknown contract
        
        # Unverified contract
        if not contract_data.get('verified', False):
            risk += 0.3
        
        # Dangerous functions
        dangerous = ['mint', 'burn', 'pause', 'blacklist', 'setTax']
        functions = contract_data.get('functions', [])
        
        for func in dangerous:
            if func in functions:
                risk += 0.1
        
        # Ownership
        if contract_data.get('owner_renounced', False):
            risk -= 0.1  # Lower risk
        else:
            owner = contract_data.get('owner', '')
            if owner:
                # Check if owner has suspicious history
                if contract_data.get('owner_rug_history', 0) > 0:
                    risk += 0.3
        
        # Proxy contract
        if contract_data.get('is_proxy', False):
            risk += 0.15
        
        return max(0, min(1.0, risk))
    
    async def _assess_developer_risk(
        self,
        developer_reputation: Optional[float]
    ) -> float:
        """Assess developer-related risk"""
        
        if developer_reputation is None:
            return 0.5  # Unknown developer
        
        # Convert reputation score to risk (inverse)
        risk = 1 - (developer_reputation / 100)
        
        return risk
    
    async def _assess_volume_risk(
        self,
        pair: TokenPair,
        volume_authenticity: Optional[float]
    ) -> float:
        """Assess volume manipulation risk"""
        
        risk = 0.0
        
        if volume_authenticity is not None:
            # Lower authenticity = higher risk
            risk = 1 - (volume_authenticity / 100)
        else:
            # Estimate from available data
            if pair.volume_24h > 0 and pair.txns_24h_buy + pair.txns_24h_sell > 0:
                avg_trade = pair.volume_24h / (pair.txns_24h_buy + pair.txns_24h_sell)
                
                # Very large average trades might indicate manipulation
                if avg_trade > 10000:
                    risk += 0.2
                
                # Unusual buy/sell balance
                if pair.txns_24h_buy > 0 and pair.txns_24h_sell > 0:
                    ratio = pair.txns_24h_buy / pair.txns_24h_sell
                    if 0.9 < ratio < 1.1:
                        risk += 0.15  # Too balanced might be wash trading
        
        return min(1.0, risk)
    
    async def _check_early_warnings(
        self,
        pair: TokenPair,
        contract_data: Optional[Dict],
        holder_data: Optional[List[Dict]]
    ) -> List[str]:
        """Check for early warning signs"""
        
        warnings = []
        warning_signs = self.prob_config.early_warning_signs
        
        # Check liquidity unlock
        if contract_data:
            lock_time = contract_data.get('lock_time_days', 0)
            lock_remaining = contract_data.get('lock_remaining_days', lock_time)
            
            if lock_remaining is not None and lock_remaining < 7:
                warnings.append("Liquidity unlock imminent")
        
        # Check developer wallet movement
        if contract_data:
            dev_wallet = contract_data.get('developer_wallet', {})
            if dev_wallet.get('recent_transfers', False):
                warnings.append("Developer wallet showing activity")
        
        # Check sudden holder concentration
        if holder_data:
            recent_changes = any(
                h.get('recent_large_increase', False)
                for h in holder_data[:5]
            )
            if recent_changes:
                warnings.append("Sudden holder concentration change")
        
        # Check volume spike without price action
        if pair.volume_24h > 0 and pair.price_change_24h is not None:
            volume_spike = pair.volume_24h > 50000 and pair.volume_1h > pair.volume_24h / 10
            price_stagnant = abs(pair.price_change_24h) < 5
            
            if volume_spike and price_stagnant:
                warnings.append("Volume spike without price movement")
        
        return warnings
    
    def _determine_warning_level(self, probability: float) -> WarningLevel:
        """Determine warning level from probability"""
        
        levels = self.prob_config.warning_levels
        
        if probability <= levels.get('low', {}).get('max_probability', 0.2):
            return WarningLevel.LOW
        elif probability <= levels.get('medium', {}).get('max_probability', 0.4):
            return WarningLevel.MEDIUM
        elif probability <= levels.get('high', {}).get('max_probability', 0.6):
            return WarningLevel.HIGH
        else:
            return WarningLevel.CRITICAL
    
    def _get_recommended_action(
        self,
        level: WarningLevel,
        probability: float
    ) -> str:
        """Get recommended action based on warning level"""
        
        actions = {
            WarningLevel.LOW: "Monitor normally - standard risk",
            WarningLevel.MEDIUM: "Exercise caution - elevated risk detected",
            WarningLevel.HIGH: "Consider exit - high rug probability",
            WarningLevel.CRITICAL: "URGENT: Exit immediately - critical risk"
        }
        
        return actions.get(level, "Unknown risk level")
    
    def _calculate_confidence(self, component_scores: Dict[str, float]) -> float:
        """Calculate confidence in probability estimate"""
        
        # More components with data = higher confidence
        non_zero_components = sum(1 for v in component_scores.values() if v > 0)
        
        base_confidence = non_zero_components / len(component_scores)
        
        # Adjust based on score variance
        if len(component_scores) > 1:
            values = list(component_scores.values())
            variance = sum((v - sum(values)/len(values))**2 for v in values) / len(values)
            
            # High variance reduces confidence slightly
            if variance > 0.1:
                base_confidence *= 0.9
        
        return base_confidence
    
    async def _store_probability(
        self,
        token_address: str,
        probability: RugProbability
    ):
        """Store probability in history"""
        
        async with self._lock:
            if token_address not in self._probability_history:
                self._probability_history[token_address] = []
            
            self._probability_history[token_address].append({
                'timestamp': get_timestamp(),
                'probability': probability.probability,
                'level': probability.warning_level.value
            })
            
            # Keep only last 100 entries
            self._probability_history[token_address] = \
                self._probability_history[token_address][-100:]
    
    async def get_probability_trend(
        self,
        token_address: str,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get probability trend over time"""
        
        cutoff = get_timestamp() - (hours * 3600)
        
        async with self._lock:
            history = [
                h for h in self._probability_history.get(token_address, [])
                if h['timestamp'] > cutoff
            ]
        
        if len(history) < 2:
            return {
                'trend': 'insufficient_data',
                'change': 0,
                'current': history[-1]['probability'] if history else 0
            }
        
        # Calculate trend
        recent = [h['probability'] for h in history[-10:]]
        older = [h['probability'] for h in history[:-10]] if len(history) > 10 else recent[:5]
        
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else recent_avg
        
        change = recent_avg - older_avg
        
        if change > 0.2:
            trend = 'rapidly_increasing'
        elif change > 0.05:
            trend = 'increasing'
        elif change < -0.2:
            trend = 'rapidly_decreasing'
        elif change < -0.05:
            trend = 'decreasing'
        else:
            trend = 'stable'
        
        return {
            'trend': trend,
            'change': round(change, 4),
            'current': round(recent[-1], 4),
            'average': round(recent_avg, 4),
            'max': round(max(h['probability'] for h in history), 4),
            'min': round(min(h['probability'] for h in history), 4)
        }
    
    async def cleanup(self):
        """Clean up old probability data"""
        
        cutoff = get_timestamp() - (7 * 86400)  # 7 days
        
        async with self._lock:
            # Clean history
            for token in list(self._probability_history.keys()):
                self._probability_history[token] = [
                    h for h in self._probability_history[token]
                    if h['timestamp'] > cutoff
                ]
                if not self._probability_history[token]:
                    del self._probability_history[token]


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_probability_estimator: Optional[RugProbabilityEstimator] = None


def get_probability_estimator() -> RugProbabilityEstimator:
    """Get or create rug probability estimator singleton"""
    global _probability_estimator
    if _probability_estimator is None:
        _probability_estimator = RugProbabilityEstimator()
    return _probability_estimator
