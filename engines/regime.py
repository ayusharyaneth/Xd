# ============================================================
# MARKET REGIME ANALYZER
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import statistics

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp
from api.dexscreener import TokenPair


logger = get_logger("regime_engine")


class MarketRegime(Enum):
    """Market regime types"""
    BULL = "bull"
    BEAR = "bear"
    CHOP = "chop"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class RegimeState:
    """Current market regime state"""
    regime: MarketRegime
    confidence: float
    duration_seconds: int
    indicators: Dict[str, Any]
    threshold_adjustments: Dict[str, float]
    timestamp: int = field(default_factory=get_timestamp)


@dataclass
class RegimeMetrics:
    """Metrics for regime detection"""
    price_trend: str  # 'up', 'down', 'sideways'
    volume_trend: str  # 'up', 'down', 'stable'
    volatility: float
    sentiment: str  # 'positive', 'negative', 'neutral'
    breadth: float  # Market breadth


class MarketRegimeAnalyzer:
    """Analyze and track market regime"""
    
    def __init__(self):
        self.config = get_config()
        self.regime_config = self.config.strategy.market_regime
        self._price_history: deque = deque(maxlen=100)
        self._volume_history: deque = deque(maxlen=100)
        self._regime_history: List[RegimeState] = []
        self._current_regime: Optional[RegimeState] = None
        self._regime_start_time: int = get_timestamp()
        self._lock = asyncio.Lock()
    
    async def update_metrics(
        self,
        pairs: List[TokenPair]
    ):
        """Update market metrics from current pairs"""
        
        if not pairs:
            return
        
        # Calculate aggregate metrics
        avg_price_change = sum(p.price_change_24h for p in pairs) / len(pairs)
        avg_volume = sum(p.volume_24h for p in pairs) / len(pairs)
        
        # Count positive vs negative
        positive = sum(1 for p in pairs if p.price_change_24h > 0)
        negative = len(pairs) - positive
        
        # Calculate volatility (standard deviation of price changes)
        if len(pairs) > 1:
            volatility = statistics.stdev(p.price_change_24h for p in pairs)
        else:
            volatility = 0
        
        async with self._lock:
            self._price_history.append({
                'timestamp': get_timestamp(),
                'avg_change': avg_price_change,
                'positive_count': positive,
                'negative_count': negative
            })
            
            self._volume_history.append({
                'timestamp': get_timestamp(),
                'avg_volume': avg_volume
            })
    
    async def analyze_regime(self) -> RegimeState:
        """Analyze current market regime"""
        
        async with self._lock:
            price_data = list(self._price_history)
            volume_data = list(self._volume_history)
        
        if len(price_data) < 5:
            return RegimeState(
                regime=MarketRegime.UNKNOWN,
                confidence=0.5,
                duration_seconds=0,
                indicators={},
                threshold_adjustments={}
            )
        
        # Calculate regime metrics
        metrics = self._calculate_metrics(price_data, volume_data)
        
        # Determine regime
        regime, confidence = self._determine_regime(metrics)
        
        # Get threshold adjustments
        adjustments = self._get_threshold_adjustments(regime)
        
        # Calculate duration
        duration = get_timestamp() - self._regime_start_time
        
        # Check if regime changed
        if self._current_regime and self._current_regime.regime != regime:
            self._regime_start_time = get_timestamp()
            duration = 0
            
            # Store old regime
            self._regime_history.append(self._current_regime)
            
            # Keep only last 100 regimes
            if len(self._regime_history) > 100:
                self._regime_history = self._regime_history[-100:]
        
        regime_state = RegimeState(
            regime=regime,
            confidence=round(confidence, 2),
            duration_seconds=duration,
            indicators={
                'price_trend': metrics.price_trend,
                'volume_trend': metrics.volume_trend,
                'volatility': round(metrics.volatility, 2),
                'sentiment': metrics.sentiment,
                'breadth': round(metrics.breadth, 2)
            },
            threshold_adjustments=adjustments
        )
        
        async with self._lock:
            self._current_regime = regime_state
        
        return regime_state
    
    def _calculate_metrics(
        self,
        price_data: List[Dict],
        volume_data: List[Dict]
    ) -> RegimeMetrics:
        """Calculate regime metrics from historical data"""
        
        # Price trend
        recent_prices = [p['avg_change'] for p in price_data[-10:]]
        older_prices = [p['avg_change'] for p in price_data[:-10]] if len(price_data) > 10 else recent_prices[:5]
        
        recent_avg = sum(recent_prices) / len(recent_prices) if recent_prices else 0
        older_avg = sum(older_prices) / len(older_prices) if older_prices else 0
        
        if recent_avg > older_avg * 1.1 and recent_avg > 5:
            price_trend = 'up'
        elif recent_avg < older_avg * 0.9 and recent_avg < -5:
            price_trend = 'down'
        else:
            price_trend = 'sideways'
        
        # Volume trend
        recent_volumes = [v['avg_volume'] for v in volume_data[-5:]]
        older_volumes = [v['avg_volume'] for v in volume_data[:-5]] if len(volume_data) > 5 else recent_volumes[:3]
        
        recent_vol_avg = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
        older_vol_avg = sum(older_volumes) / len(older_volumes) if older_volumes else 0
        
        if recent_vol_avg > older_vol_avg * 1.2:
            volume_trend = 'up'
        elif recent_vol_avg < older_vol_avg * 0.8:
            volume_trend = 'down'
        else:
            volume_trend = 'stable'
        
        # Volatility
        if len(recent_prices) > 1:
            volatility = statistics.stdev(recent_prices)
        else:
            volatility = 0
        
        # Sentiment
        positive_ratio = sum(p['positive_count'] for p in price_data[-5:]) / max(1, sum(
            p['positive_count'] + p['negative_count'] for p in price_data[-5:]
        ))
        
        if positive_ratio > 0.6:
            sentiment = 'positive'
        elif positive_ratio < 0.4:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        # Breadth
        breadth = positive_ratio
        
        return RegimeMetrics(
            price_trend=price_trend,
            volume_trend=volume_trend,
            volatility=volatility,
            sentiment=sentiment,
            breadth=breadth
        )
    
    def _determine_regime(
        self,
        metrics: RegimeMetrics
    ) -> Tuple[MarketRegime, float]:
        """Determine market regime from metrics"""
        
        regime_types = self.regime_config.regime_types
        
        # Score each regime
        scores = {}
        
        # Bull regime
        bull_score = 0
        bull_indicators = regime_types.get('bull', {}).get('indicators', {})
        if metrics.price_trend == bull_indicators.get('price_trend'):
            bull_score += 0.4
        if metrics.volume_trend == bull_indicators.get('volume_trend'):
            bull_score += 0.3
        if metrics.sentiment == bull_indicators.get('sentiment'):
            bull_score += 0.3
        scores[MarketRegime.BULL] = bull_score
        
        # Bear regime
        bear_score = 0
        bear_indicators = regime_types.get('bear', {}).get('indicators', {})
        if metrics.price_trend == bear_indicators.get('price_trend'):
            bear_score += 0.4
        if metrics.sentiment == bear_indicators.get('sentiment'):
            bear_score += 0.3
        scores[MarketRegime.BEAR] = bear_score
        
        # Chop regime
        chop_score = 0
        chop_indicators = regime_types.get('chop', {}).get('indicators', {})
        if metrics.price_trend == chop_indicators.get('price_trend'):
            chop_score += 0.4
        if metrics.volume_trend == chop_indicators.get('volume_trend'):
            chop_score += 0.3
        scores[MarketRegime.CHOP] = chop_score
        
        # Volatile regime
        vol_score = 0
        if metrics.volatility > 20:
            vol_score += 0.5
        if metrics.price_trend == 'sideways' and metrics.volatility > 15:
            vol_score += 0.3
        scores[MarketRegime.VOLATILE] = vol_score
        
        # Select highest scoring regime
        best_regime = max(scores, key=scores.get)
        best_score = scores[best_regime]
        
        # Calculate confidence
        total_score = sum(scores.values())
        confidence = best_score / total_score if total_score > 0 else 0.5
        
        return best_regime, confidence
    
    def _get_threshold_adjustments(
        self,
        regime: MarketRegime
    ) -> Dict[str, float]:
        """Get threshold adjustments for current regime"""
        
        regime_types = self.regime_config.regime_types
        
        adjustments = regime_types.get(regime.value, {}).get('threshold_adjustments', {})
        
        return {
            'risk_tolerance': adjustments.get('risk_tolerance', 1.0),
            'volume_requirement': adjustments.get('volume_requirement', 1.0),
            'profit_target_multiplier': adjustments.get('profit_target_multiplier', 1.0)
        }
    
    async def get_current_regime(self) -> Optional[RegimeState]:
        """Get current market regime"""
        async with self._lock:
            return self._current_regime
    
    async def get_regime_summary(self) -> Dict[str, Any]:
        """Get summary of current regime"""
        
        regime = await self.get_current_regime()
        
        if not regime:
            return {
                'regime': 'unknown',
                'confidence': 0,
                'duration_minutes': 0,
                'message': 'Insufficient data to determine regime'
            }
        
        regime_messages = {
            MarketRegime.BULL: "Bull market - favorable conditions for entries",
            MarketRegime.BEAR: "Bear market - exercise caution, focus on quality",
            MarketRegime.CHOP: "Choppy market - reduce position sizes",
            MarketRegime.VOLATILE: "Volatile market - use tight stops",
            MarketRegime.UNKNOWN: "Regime unclear - proceed with caution"
        }
        
        return {
            'regime': regime.regime.value,
            'confidence': regime.confidence,
            'duration_minutes': regime.duration_seconds // 60,
            'indicators': regime.indicators,
            'threshold_adjustments': regime.threshold_adjustments,
            'message': regime_messages.get(regime.regime, 'Unknown regime')
        }
    
    async def should_adjust_for_regime(
        self,
        base_threshold: float,
        adjustment_type: str = 'risk_tolerance'
    ) -> float:
        """Get regime-adjusted threshold"""
        
        regime = await self.get_current_regime()
        
        if not regime:
            return base_threshold
        
        adjustment = regime.threshold_adjustments.get(adjustment_type, 1.0)
        
        return base_threshold * adjustment
    
    async def get_regime_history(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get regime change history"""
        
        async with self._lock:
            history = self._regime_history[-limit:]
        
        return [
            {
                'regime': h.regime.value,
                'confidence': h.confidence,
                'duration_minutes': h.duration_seconds // 60,
                'timestamp': h.timestamp
            }
            for h in history
        ]


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_regime_analyzer: Optional[MarketRegimeAnalyzer] = None


def get_regime_analyzer() -> MarketRegimeAnalyzer:
    """Get or create regime analyzer singleton"""
    global _regime_analyzer
    if _regime_analyzer is None:
        _regime_analyzer = MarketRegimeAnalyzer()
    return _regime_analyzer
