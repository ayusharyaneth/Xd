# ============================================================
# ALERT RANKING ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import heapq

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp
from api.dexscreener import TokenPair


logger = get_logger("ranking_engine")


@dataclass
class RankedAlert:
    """Ranked alert with composite score"""
    token_address: str
    token_symbol: str
    composite_score: float
    component_scores: Dict[str, float]
    rank: int
    timestamp: int
    urgency: str
    alert_type: str
    summary: str


@dataclass
class AlertBuffer:
    """Buffer for alerts in time window"""
    alerts: List[RankedAlert] = field(default_factory=list)
    window_start: int = field(default_factory=get_timestamp)
    
    def is_full(self, max_alerts: int) -> bool:
        return len(self.alerts) >= max_alerts
    
    def is_expired(self, window_seconds: int) -> bool:
        return get_timestamp() - self.window_start > window_seconds


class AlertRankingEngine:
    """Rank and prioritize alerts"""
    
    def __init__(self):
        self.config = get_config()
        self.ranking_config = self.config.strategy.alert_ranking
        self._alert_buffer: AlertBuffer = AlertBuffer()
        self._token_scores: Dict[str, List[Dict]] = defaultdict(list)
        self._sent_alerts: Dict[str, int] = {}  # Track sent alerts for cooldown
        self._lock = asyncio.Lock()
    
    async def calculate_composite_score(
        self,
        pair: TokenPair,
        risk_score: Optional[float] = None,
        volume_quality: Optional[float] = None,
        buy_quality: Optional[float] = None,
        developer_reputation: Optional[float] = None,
        whale_activity: Optional[float] = None,
        early_buyer_quality: Optional[float] = None,
        capital_rotation: Optional[float] = None,
        rug_probability: Optional[float] = None
    ) -> Dict[str, float]:
        """Calculate composite score for ranking"""
        
        weights = self.ranking_config.composite_score_weights
        
        # Normalize all scores to 0-100 scale
        normalized = {
            'risk_score': 100 - (risk_score or 50),  # Invert - lower risk is better
            'volume_quality': volume_quality or 50,
            'buy_quality': buy_quality or 50,
            'developer_reputation': developer_reputation or 50,
            'whale_activity': whale_activity or 50,
            'early_buyer_quality': early_buyer_quality or 50,
            'capital_rotation': capital_rotation or 50,
            'rug_probability': 100 - ((rug_probability or 0.5) * 100)  # Invert
        }
        
        # Calculate weighted composite
        composite = 0
        component_scores = {}
        
        for key, value in normalized.items():
            weight = weights.get(key, 0)
            weighted_score = value * weight
            composite += weighted_score
            component_scores[key] = round(value, 2)
        
        # Add momentum bonus
        momentum = await self._calculate_momentum(pair)
        composite += momentum * 5  # Small momentum bonus
        component_scores['momentum'] = round(momentum, 2)
        
        # Add new token bonus
        if pair.is_new_pair:
            composite += 5
            component_scores['new_token_bonus'] = 5
        
        return {
            'composite': round(composite, 2),
            'components': component_scores
        }
    
    async def _calculate_momentum(self, pair: TokenPair) -> float:
        """Calculate price momentum factor"""
        
        momentum = 0
        
        # Price change momentum
        if pair.price_change_5m > 10:
            momentum += 2
        elif pair.price_change_5m > 5:
            momentum += 1
        
        if pair.price_change_1h > 20:
            momentum += 3
        elif pair.price_change_1h > 10:
            momentum += 2
        
        # Volume momentum
        if pair.volume_24h > 100000:
            momentum += 1
        
        # Buy pressure
        if pair.buy_ratio > 0.6:
            momentum += 1
        
        return momentum
    
    async def rank_alert(
        self,
        pair: TokenPair,
        **scores
    ) -> Optional[RankedAlert]:
        """Create and rank an alert"""
        
        # Check cooldown
        if await self._is_on_cooldown(pair.token_address):
            return None
        
        # Calculate composite score
        result = await self.calculate_composite_score(pair, **scores)
        composite = result['composite']
        components = result['components']
        
        # Check minimum score
        min_score = self.ranking_config.ranking_limits.get('min_score_to_alert', 50)
        if composite < min_score:
            return None
        
        # Determine urgency
        urgency = self._determine_urgency(composite, components)
        
        # Determine alert type
        alert_type = self._determine_alert_type(components)
        
        # Create summary
        summary = self._generate_summary(pair, components, urgency)
        
        ranked = RankedAlert(
            token_address=pair.token_address,
            token_symbol=pair.token_symbol,
            composite_score=composite,
            component_scores=components,
            rank=0,  # Will be set when added to buffer
            timestamp=get_timestamp(),
            urgency=urgency,
            alert_type=alert_type,
            summary=summary
        )
        
        return ranked
    
    def _determine_urgency(self, composite: float, components: Dict[str, float]) -> str:
        """Determine alert urgency"""
        
        if composite >= 80:
            return "critical"
        elif composite >= 65:
            return "high"
        elif composite >= 50:
            return "medium"
        else:
            return "low"
    
    def _determine_alert_type(self, components: Dict[str, float]) -> str:
        """Determine type of alert based on strongest components"""
        
        # Find highest scoring components
        sorted_components = sorted(
            components.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        top_component = sorted_components[0][0] if sorted_components else 'general'
        
        type_mapping = {
            'whale_activity': 'whale_alert',
            'volume_quality': 'volume_alert',
            'buy_quality': 'momentum_alert',
            'early_buyer_quality': 'early_entry_alert',
            'capital_rotation': 'rotation_alert',
            'developer_reputation': 'quality_alert',
            'risk_score': 'opportunity_alert',
            'rug_probability': 'caution_alert'
        }
        
        return type_mapping.get(top_component, 'general_alert')
    
    def _generate_summary(
        self,
        pair: TokenPair,
        components: Dict[str, float],
        urgency: str
    ) -> str:
        """Generate alert summary"""
        
        summaries = []
        
        if pair.is_new_pair:
            summaries.append(f"New token ({pair.token_symbol})")
        
        if components.get('whale_activity', 0) > 70:
            summaries.append("Strong whale interest")
        
        if components.get('buy_quality', 0) > 70:
            summaries.append("High-quality buying")
        
        if components.get('volume_quality', 0) > 70:
            summaries.append("Authentic volume")
        
        if components.get('capital_rotation', 0) > 70:
            summaries.append("Capital rotating in")
        
        if pair.price_change_5m > 10:
            summaries.append(f"+{pair.price_change_5m:.1f}% in 5m")
        
        if not summaries:
            summaries.append(f"{pair.token_symbol} showing interesting activity")
        
        return " | ".join(summaries)
    
    async def add_to_buffer(
        self,
        alert: RankedAlert
    ) -> Tuple[bool, Optional[List[RankedAlert]]]:
        """Add alert to buffer, returns (added, top_alerts_to_send)"""
        
        buffer_config = self.ranking_config.buffer_window
        
        if not buffer_config.enabled:
            return True, [alert]
        
        async with self._lock:
            # Check if buffer expired
            if self._alert_buffer.is_expired(buffer_config.window_seconds):
                # Process old buffer
                old_alerts = self._alert_buffer.alerts
                self._alert_buffer = AlertBuffer()
                
                # Get top N from old buffer
                top_n = self.ranking_config.ranking_limits.get('top_n_alerts', 10)
                top_alerts = heapq.nlargest(
                    top_n,
                    old_alerts,
                    key=lambda a: a.composite_score
                )
                
                # Add new alert to new buffer
                self._alert_buffer.alerts.append(alert)
                
                return True, top_alerts
            
            # Check if buffer is full
            if self._alert_buffer.is_full(buffer_config.max_alerts_in_window):
                # Get minimum score in buffer
                min_score = min(a.composite_score for a in self._alert_buffer.alerts)
                
                if alert.composite_score > min_score:
                    # Replace lowest score alert
                    self._alert_buffer.alerts = [
                        a for a in self._alert_buffer.alerts
                        if a.composite_score > min_score
                    ]
                    self._alert_buffer.alerts.append(alert)
                    return True, None
                else:
                    return False, None
            
            # Add to buffer
            self._alert_buffer.alerts.append(alert)
            return True, None
    
    async def flush_buffer(self) -> List[RankedAlert]:
        """Force flush the buffer and return all alerts"""
        
        async with self._lock:
            alerts = self._alert_buffer.alerts
            self._alert_buffer = AlertBuffer()
        
        # Sort by score
        alerts.sort(key=lambda a: a.composite_score, reverse=True)
        
        # Assign ranks
        for i, alert in enumerate(alerts):
            alert.rank = i + 1
        
        return alerts
    
    async def _is_on_cooldown(self, token_address: str) -> bool:
        """Check if token is on cooldown"""
        
        cooldown_seconds = self.config.settings.ALERT_COOLDOWN_SECONDS
        
        async with self._lock:
            last_sent = self._sent_alerts.get(token_address, 0)
        
        return get_timestamp() - last_sent < cooldown_seconds
    
    async def mark_alert_sent(self, token_address: str):
        """Mark that an alert was sent for token"""
        async with self._lock:
            self._sent_alerts[token_address] = get_timestamp()
    
    async def get_top_alerts(
        self,
        limit: int = 10,
        min_score: Optional[float] = None
    ) -> List[RankedAlert]:
        """Get top ranked alerts from buffer"""
        
        async with self._lock:
            alerts = self._alert_buffer.alerts.copy()
        
        # Filter by min score
        if min_score:
            alerts = [a for a in alerts if a.composite_score >= min_score]
        
        # Sort and limit
        alerts.sort(key=lambda a: a.composite_score, reverse=True)
        
        # Assign ranks
        for i, alert in enumerate(alerts[:limit]):
            alert.rank = i + 1
        
        return alerts[:limit]
    
    async def get_token_ranking_history(
        self,
        token_address: str
    ) -> List[Dict[str, Any]]:
        """Get ranking history for a token"""
        
        async with self._lock:
            history = self._token_scores.get(token_address, [])
        
        return [
            {
                'timestamp': h['timestamp'],
                'composite_score': h['composite'],
                'components': h['components']
            }
            for h in history[-20:]  # Last 20 entries
        ]
    
    async def store_token_score(
        self,
        token_address: str,
        composite: float,
        components: Dict[str, float]
    ):
        """Store score for token history"""
        
        async with self._lock:
            self._token_scores[token_address].append({
                'timestamp': get_timestamp(),
                'composite': composite,
                'components': components
            })
            
            # Keep only last 100 entries
            self._token_scores[token_address] = \
                self._token_scores[token_address][-100:]
    
    async def get_ranking_stats(self) -> Dict[str, Any]:
        """Get ranking engine statistics"""
        
        async with self._lock:
            buffer_size = len(self._alert_buffer.alerts)
            window_age = get_timestamp() - self._alert_buffer.window_start
            
            return {
                'buffer_size': buffer_size,
                'buffer_max': self.ranking_config.buffer_window.max_alerts_in_window,
                'window_age_seconds': window_age,
                'window_expires_in': max(0, self.ranking_config.buffer_window.window_seconds - window_age),
                'tracked_tokens': len(self._token_scores),
                'alerts_in_cooldown': len(self._sent_alerts)
            }
    
    async def cleanup(self):
        """Clean up old data"""
        
        cutoff = get_timestamp() - 86400  # 24 hours
        
        async with self._lock:
            # Clean old scores
            for token in list(self._token_scores.keys()):
                self._token_scores[token] = [
                    s for s in self._token_scores[token]
                    if s['timestamp'] > cutoff
                ]
                if not self._token_scores[token]:
                    del self._token_scores[token]
            
            # Clean sent alerts tracking
            self._sent_alerts = {
                k: v for k, v in self._sent_alerts.items()
                if v > cutoff
            }


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_ranking_engine: Optional[AlertRankingEngine] = None


def get_ranking_engine() -> AlertRankingEngine:
    """Get or create ranking engine singleton"""
    global _ranking_engine
    if _ranking_engine is None:
        _ranking_engine = AlertRankingEngine()
    return _ranking_engine
