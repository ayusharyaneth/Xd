# ============================================================
# WATCH MODE MANAGER
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, format_duration, format_currency
from api.dexscreener import TokenPair


logger = get_logger("watch_manager")


class WatchStatus(Enum):
    """Watch status"""
    ACTIVE = "active"
    ESCALATED = "escalated"
    EXPIRED = "expired"
    REMOVED = "removed"


@dataclass
class WatchedToken:
    """Represents a watched token"""
    token_address: str
    token_symbol: str
    chain_id: str
    added_at: int
    expires_at: int
    added_by: str
    initial_price: float
    initial_volume: float
    initial_risk_score: float
    status: WatchStatus = WatchStatus.ACTIVE
    
    # Tracking
    price_history: List[Dict] = field(default_factory=list)
    alerts_sent: int = 0
    last_alert_at: Optional[int] = None
    escalation_count: int = 0
    
    # Current state
    current_price: float = 0.0
    current_volume: float = 0.0
    current_risk_score: float = 0.0
    price_change_percent: float = 0.0
    volume_change_percent: float = 0.0
    risk_change: float = 0.0


@dataclass
class WatchAlert:
    """Alert from watch mode"""
    token_address: str
    alert_type: str
    severity: str
    message: str
    metrics: Dict[str, Any]
    timestamp: int


class WatchManager:
    """Manage watch mode for tokens"""
    
    def __init__(self):
        self.config = get_config()
        self.watch_config = self.config.strategy.watch_mode
        self._watched_tokens: Dict[str, WatchedToken] = {}
        self._watch_alerts: List[WatchAlert] = []
        self._lock = asyncio.Lock()
    
    async def add_watch(
        self,
        pair: TokenPair,
        added_by: str,
        risk_score: Optional[float] = None,
        custom_duration_minutes: Optional[int] = None
    ) -> WatchedToken:
        """Add a token to watch list"""
        
        token_address = pair.token_address
        
        # Check if already watching
        async with self._lock:
            if token_address in self._watched_tokens:
                # Extend existing watch
                existing = self._watched_tokens[token_address]
                existing.expires_at = get_timestamp() + (
                    custom_duration_minutes or self.watch_config.monitoring.expiry_minutes
                ) * 60
                logger.info(f"Extended watch for {pair.token_symbol}")
                return existing
            
            # Check max watches
            if len(self._watched_tokens) >= self.watch_config.monitoring.max_concurrent:
                # Remove oldest
                oldest = min(
                    self._watched_tokens.values(),
                    key=lambda w: w.added_at
                )
                del self._watched_tokens[oldest.token_address]
                logger.info(f"Removed oldest watch to make room: {oldest.token_symbol}")
        
        # Create new watch
        duration = custom_duration_minutes or self.watch_config.monitoring.expiry_minutes
        
        watch = WatchedToken(
            token_address=token_address,
            token_symbol=pair.token_symbol,
            chain_id=pair.chain_id,
            added_at=get_timestamp(),
            expires_at=get_timestamp() + duration * 60,
            added_by=added_by,
            initial_price=pair.price_usd,
            initial_volume=pair.volume_24h,
            initial_risk_score=risk_score or 50,
            current_price=pair.price_usd,
            current_volume=pair.volume_24h,
            current_risk_score=risk_score or 50
        )
        
        async with self._lock:
            self._watched_tokens[token_address] = watch
        
        logger.info(f"Added watch for {pair.token_symbol} by {added_by}")
        
        return watch
    
    async def remove_watch(
        self,
        token_address: str,
        removed_by: Optional[str] = None
    ) -> bool:
        """Remove a token from watch list"""
        
        async with self._lock:
            if token_address in self._watched_tokens:
                watch = self._watched_tokens[token_address]
                watch.status = WatchStatus.REMOVED
                del self._watched_tokens[token_address]
                logger.info(f"Removed watch for {watch.token_symbol} by {removed_by or 'system'}")
                return True
        
        return False
    
    async def update_watch(
        self,
        token_address: str,
        pair: TokenPair,
        risk_score: Optional[float] = None
    ) -> Optional[WatchAlert]:
        """Update watched token with new data"""
        
        async with self._lock:
            watch = self._watched_tokens.get(token_address)
        
        if not watch:
            return None
        
        # Check if expired
        if get_timestamp() > watch.expires_at:
            watch.status = WatchStatus.EXPIRED
            await self.remove_watch(token_address, 'expiry')
            return None
        
        # Update current state
        watch.current_price = pair.price_usd
        watch.current_volume = pair.volume_24h
        if risk_score is not None:
            watch.current_risk_score = risk_score
        
        # Calculate changes
        if watch.initial_price > 0:
            watch.price_change_percent = (
                (watch.current_price - watch.initial_price) / watch.initial_price * 100
            )
        
        if watch.initial_volume > 0:
            watch.volume_change_percent = (
                (watch.current_volume - watch.initial_volume) / watch.initial_volume * 100
            )
        
        watch.risk_change = watch.current_risk_score - watch.initial_risk_score
        
        # Add to history
        watch.price_history.append({
            'timestamp': get_timestamp(),
            'price': watch.current_price,
            'volume': watch.current_volume,
            'risk': watch.current_risk_score
        })
        
        # Keep history manageable
        if len(watch.price_history) > 100:
            watch.price_history = watch.price_history[-100:]
        
        # Check for escalation
        alert = await self._check_escalation(watch, pair)
        
        return alert
    
    async def _check_escalation(
        self,
        watch: WatchedToken,
        pair: TokenPair
    ) -> Optional[WatchAlert]:
        """Check for escalation conditions"""
        
        escalation = self.watch_config.escalation
        
        # Check price escalation
        if abs(watch.price_change_percent) >= escalation.price_change_threshold:
            severity = 'high' if abs(watch.price_change_percent) >= 50 else 'medium'
            direction = 'up' if watch.price_change_percent > 0 else 'down'
            
            alert = WatchAlert(
                token_address=watch.token_address,
                alert_type=f'price_{direction}',
                severity=severity,
                message=f"Price moved {watch.price_change_percent:+.1f}% since watching",
                metrics={
                    'initial_price': watch.initial_price,
                    'current_price': watch.current_price,
                    'change_percent': watch.price_change_percent
                },
                timestamp=get_timestamp()
            )
            
            watch.escalation_count += 1
            if watch.escalation_count >= self.config.settings.WATCH_ESCALATION_THRESHOLD:
                watch.status = WatchStatus.ESCALATED
            
            await self._store_alert(alert)
            return alert
        
        # Check volume escalation
        if watch.volume_change_percent >= escalation.volume_spike_threshold * 100:
            alert = WatchAlert(
                token_address=watch.token_address,
                alert_type='volume_spike',
                severity='medium',
                message=f"Volume spiked {watch.volume_change_percent:.1f}x since watching",
                metrics={
                    'initial_volume': watch.initial_volume,
                    'current_volume': watch.current_volume,
                    'spike_ratio': watch.volume_change_percent / 100
                },
                timestamp=get_timestamp()
            )
            
            await self._store_alert(alert)
            return alert
        
        # Check risk escalation
        if watch.risk_change >= escalation.risk_score_change:
            alert = WatchAlert(
                token_address=watch.token_address,
                alert_type='risk_escalation',
                severity='high',
                message=f"Risk score increased by {watch.risk_change:.0f} points",
                metrics={
                    'initial_risk': watch.initial_risk_score,
                    'current_risk': watch.current_risk_score,
                    'change': watch.risk_change
                },
                timestamp=get_timestamp()
            )
            
            await self._store_alert(alert)
            return alert
        
        return None
    
    async def _store_alert(self, alert: WatchAlert):
        """Store watch alert"""
        async with self._lock:
            self._watch_alerts.append(alert)
            
            # Keep only recent alerts
            cutoff = get_timestamp() - 86400
            self._watch_alerts = [
                a for a in self._watch_alerts
                if a.timestamp > cutoff
            ]
    
    async def get_watched_tokens(
        self,
        status: Optional[WatchStatus] = None
    ) -> List[WatchedToken]:
        """Get list of watched tokens"""
        
        async with self._lock:
            watches = list(self._watched_tokens.values())
        
        if status:
            watches = [w for w in watches if w.status == status]
        
        return watches
    
    async def get_watch_summary(
        self,
        token_address: str
    ) -> Optional[Dict[str, Any]]:
        """Get summary of a watched token"""
        
        async with self._lock:
            watch = self._watched_tokens.get(token_address)
        
        if not watch:
            return None
        
        time_remaining = max(0, watch.expires_at - get_timestamp())
        
        return {
            'token_symbol': watch.token_symbol,
            'token_address': watch.token_address,
            'status': watch.status.value,
            'added_at': watch.added_at,
            'expires_in_seconds': time_remaining,
            'added_by': watch.added_by,
            'price_change': round(watch.price_change_percent, 2),
            'volume_change': round(watch.volume_change_percent, 2),
            'risk_change': round(watch.risk_change, 2),
            'escalation_count': watch.escalation_count,
            'alerts_sent': watch.alerts_sent,
            'time_remaining': format_duration(time_remaining)
        }
    
    async def get_all_watches_summary(self) -> Dict[str, Any]:
        """Get summary of all watches"""
        
        async with self._lock:
            watches = list(self._watched_tokens.values())
        
        active = sum(1 for w in watches if w.status == WatchStatus.ACTIVE)
        escalated = sum(1 for w in watches if w.status == WatchStatus.ESCALATED)
        
        price_up = sum(1 for w in watches if w.price_change_percent > 20)
        price_down = sum(1 for w in watches if w.price_change_percent < -20)
        
        return {
            'total_watches': len(watches),
            'active': active,
            'escalated': escalated,
            'price_up_significant': price_up,
            'price_down_significant': price_down,
            'watches': [
                {
                    'symbol': w.token_symbol,
                    'price_change': round(w.price_change_percent, 2),
                    'status': w.status.value,
                    'expires_in': format_duration(w.expires_at - get_timestamp())
                }
                for w in watches[:10]
            ]
        }
    
    async def get_watch_alerts(
        self,
        token_address: Optional[str] = None,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get watch alerts"""
        
        cutoff = get_timestamp() - (hours * 3600)
        
        async with self._lock:
            alerts = [
                a for a in self._watch_alerts
                if a.timestamp > cutoff
                and (token_address is None or a.token_address == token_address)
            ]
        
        return [
            {
                'token': a.token_address,
                'type': a.alert_type,
                'severity': a.severity,
                'message': a.message,
                'metrics': a.metrics,
                'time_ago': get_timestamp() - a.timestamp
            }
            for a in alerts
        ]
    
    async def cleanup_expired(self):
        """Clean up expired watches"""
        
        current_time = get_timestamp()
        expired = []
        
        async with self._lock:
            for addr, watch in self._watched_tokens.items():
                if current_time > watch.expires_at:
                    expired.append(addr)
            
            for addr in expired:
                watch = self._watched_tokens[addr]
                watch.status = WatchStatus.EXPIRED
                del self._watched_tokens[addr]
                logger.info(f"Cleaned up expired watch: {watch.token_symbol}")
        
        return len(expired)
    
    async def is_watched(self, token_address: str) -> bool:
        """Check if token is being watched"""
        async with self._lock:
            return token_address in self._watched_tokens


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_watch_manager: Optional[WatchManager] = None


def get_watch_manager() -> WatchManager:
    """Get or create watch manager singleton"""
    global _watch_manager
    if _watch_manager is None:
        _watch_manager = WatchManager()
    return _watch_manager
