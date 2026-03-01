# ============================================================
# SELF-DEFENSE SYSTEM
# ============================================================

import asyncio
import psutil
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, format_duration


logger = get_logger("self_defense")


class SafeModeState(Enum):
    """Safe mode state"""
    NORMAL = "normal"
    SAFE_MODE = "safe_mode"
    RECOVERING = "recovering"


@dataclass
class SystemMetrics:
    """System metrics snapshot"""
    timestamp: int
    api_error_rate: float
    avg_latency_ms: float
    memory_usage_mb: float
    cpu_usage_percent: float
    consecutive_failures: int


class SelfDefenseSystem:
    """Self-defense and safe mode system"""
    
    def __init__(self):
        self.config = get_config()
        self.defense_config = self.config.strategy.self_defense
        self._state = SafeModeState.NORMAL
        self._safe_mode_start: Optional[int] = None
        self._metrics_history: deque = deque(maxlen=100)
        self._consecutive_failures = 0
        self._api_errors = deque(maxlen=50)
        self._latencies = deque(maxlen=50)
        self._lock = asyncio.Lock()
        self._safe_mode_actions_taken: List[str] = []
    
    async def record_api_call(
        self,
        success: bool,
        latency_ms: float
    ):
        """Record API call result"""
        
        async with self._lock:
            if success:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
            
            self._api_errors.append(not success)
            self._latencies.append(latency_ms)
    
    async def check_system_health(self) -> Dict[str, Any]:
        """Check system health and trigger safe mode if needed"""
        
        if not self.config.settings.ENABLE_SELF_DEFENSE:
            return {'enabled': False}
        
        # Collect current metrics
        metrics = await self._collect_metrics()
        
        async with self._lock:
            self._metrics_history.append(metrics)
        
        # Check thresholds
        should_activate = await self._should_activate_safe_mode(metrics)
        should_recover = await self._should_recover(metrics)
        
        result = {
            'state': self._state.value,
            'metrics': {
                'api_error_rate': round(metrics.api_error_rate, 4),
                'avg_latency_ms': round(metrics.avg_latency_ms, 2),
                'memory_usage_mb': round(metrics.memory_usage_mb, 2),
                'cpu_usage_percent': round(metrics.cpu_usage_percent, 2),
                'consecutive_failures': metrics.consecutive_failures
            }
        }
        
        # State transitions
        if self._state == SafeModeState.NORMAL and should_activate:
            await self._activate_safe_mode()
            result['action'] = 'safe_mode_activated'
            result['reasons'] = self._get_trigger_reasons(metrics)
        
        elif self._state == SafeModeState.SAFE_MODE and should_recover:
            await self._start_recovery()
            result['action'] = 'recovery_started'
        
        elif self._state == SafeModeState.RECOVERING and should_recover:
            await self._complete_recovery()
            result['action'] = 'recovery_completed'
        
        else:
            result['action'] = 'none'
        
        result['new_state'] = self._state.value
        
        return result
    
    async def _collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics"""
        
        # Calculate API error rate
        async with self._lock:
            error_list = list(self._api_errors)
            latency_list = list(self._latencies)
            consecutive = self._consecutive_failures
        
        api_error_rate = sum(error_list) / len(error_list) if error_list else 0
        avg_latency = sum(latency_list) / len(latency_list) if latency_list else 0
        
        # System metrics
        memory = psutil.virtual_memory()
        memory_mb = memory.used / (1024 * 1024)
        
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        return SystemMetrics(
            timestamp=get_timestamp(),
            api_error_rate=api_error_rate,
            avg_latency_ms=avg_latency,
            memory_usage_mb=memory_mb,
            cpu_usage_percent=cpu_percent,
            consecutive_failures=consecutive
        )
    
    async def _should_activate_safe_mode(
        self,
        metrics: SystemMetrics
    ) -> bool:
        """Check if safe mode should be activated"""
        
        thresholds = self.defense_config.activation_thresholds
        triggers = []
        
        if metrics.api_error_rate >= thresholds.api_error_rate:
            triggers.append('api_error_rate')
        
        if metrics.avg_latency_ms >= thresholds.avg_latency_ms:
            triggers.append('latency')
        
        if metrics.memory_usage_mb >= thresholds.memory_usage_mb:
            triggers.append('memory')
        
        if metrics.cpu_usage_percent >= thresholds.cpu_usage_percent:
            triggers.append('cpu')
        
        if metrics.consecutive_failures >= thresholds.consecutive_failures:
            triggers.append('consecutive_failures')
        
        return len(triggers) >= 1  # Activate on any trigger
    
    async def _should_recover(self, metrics: SystemMetrics) -> bool:
        """Check if system can recover from safe mode"""
        
        if self._state == SafeModeState.NORMAL:
            return False
        
        thresholds = self.defense_config.activation_thresholds
        
        # Check if all metrics are below thresholds
        healthy = (
            metrics.api_error_rate < thresholds.api_error_rate * 0.5 and
            metrics.avg_latency_ms < thresholds.avg_latency_ms * 0.5 and
            metrics.memory_usage_mb < thresholds.memory_usage_mb * 0.8 and
            metrics.cpu_usage_percent < thresholds.cpu_usage_percent * 0.8 and
            metrics.consecutive_failures == 0
        )
        
        if not healthy:
            return False
        
        # Check if enough time in safe mode
        if self._safe_mode_start:
            min_safe_mode_time = self.defense_config.recovery.exit_safe_mode_after_seconds
            time_in_safe_mode = get_timestamp() - self._safe_mode_start
            
            if time_in_safe_mode < min_safe_mode_time:
                return False
        
        return True
    
    async def _activate_safe_mode(self):
        """Activate safe mode"""
        
        self._state = SafeModeState.SAFE_MODE
        self._safe_mode_start = get_timestamp()
        self._safe_mode_actions_taken = []
        
        actions = self.defense_config.safe_mode_actions
        
        if actions.reduce_poll_frequency:
            self._safe_mode_actions_taken.append('reduce_poll_frequency')
            logger.warning("Safe mode: Reducing poll frequency")
        
        if actions.pause_non_critical_features:
            self._safe_mode_actions_taken.append('pause_non_critical_features')
            logger.warning("Safe mode: Pausing non-critical features")
        
        if actions.increase_cooldowns:
            self._safe_mode_actions_taken.append('increase_cooldowns')
            logger.warning("Safe mode: Increasing cooldowns")
        
        if actions.alert_admins:
            self._safe_mode_actions_taken.append('alert_admins')
            logger.critical("Safe mode activated - alerting admins")
        
        logger.critical(f"SAFE MODE ACTIVATED at {self._safe_mode_start}")
    
    async def _start_recovery(self):
        """Start recovery from safe mode"""
        
        self._state = SafeModeState.RECOVERING
        logger.info("Starting recovery from safe mode")
    
    async def _complete_recovery(self):
        """Complete recovery to normal mode"""
        
        self._state = SafeModeState.NORMAL
        self._safe_mode_start = None
        
        logger.info("Recovery completed - returning to normal mode")
    
    def _get_trigger_reasons(self, metrics: SystemMetrics) -> List[str]:
        """Get reasons for safe mode activation"""
        
        thresholds = self.defense_config.activation_thresholds
        reasons = []
        
        if metrics.api_error_rate >= thresholds.api_error_rate:
            reasons.append(f"API error rate: {metrics.api_error_rate:.1%}")
        
        if metrics.avg_latency_ms >= thresholds.avg_latency_ms:
            reasons.append(f"High latency: {metrics.avg_latency_ms:.0f}ms")
        
        if metrics.memory_usage_mb >= thresholds.memory_usage_mb:
            reasons.append(f"High memory: {metrics.memory_usage_mb:.0f}MB")
        
        if metrics.cpu_usage_percent >= thresholds.cpu_usage_percent:
            reasons.append(f"High CPU: {metrics.cpu_usage_percent:.1f}%")
        
        if metrics.consecutive_failures >= thresholds.consecutive_failures:
            reasons.append(f"Consecutive failures: {metrics.consecutive_failures}")
        
        return reasons
    
    async def get_safe_mode_status(self) -> Dict[str, Any]:
        """Get current safe mode status"""
        
        async with self._lock:
            state = self._state
            safe_mode_start = self._safe_mode_start
            actions = self._safe_mode_actions_taken.copy()
        
        time_in_safe_mode = None
        if state == SafeModeState.SAFE_MODE and safe_mode_start:
            time_in_safe_mode = get_timestamp() - safe_mode_start
        
        return {
            'state': state.value,
            'in_safe_mode': state != SafeModeState.NORMAL,
            'time_in_safe_mode_seconds': time_in_safe_mode,
            'time_in_safe_mode_formatted': format_duration(time_in_safe_mode) if time_in_safe_mode else None,
            'actions_taken': actions,
            'auto_recovery_enabled': self.defense_config.recovery.auto_recovery_enabled
        }
    
    def is_safe_mode(self) -> bool:
        """Check if currently in safe mode"""
        return self._state == SafeModeState.SAFE_MODE
    
    def should_reduce_features(self) -> bool:
        """Check if features should be reduced"""
        return self._state in [SafeModeState.SAFE_MODE, SafeModeState.RECOVERING]
    
    async def get_adjusted_poll_interval(self, base_interval: int) -> int:
        """Get adjusted poll interval based on safe mode"""
        
        if self._state == SafeModeState.SAFE_MODE:
            return base_interval * 2  # Double interval in safe mode
        elif self._state == SafeModeState.RECOVERING:
            return int(base_interval * 1.5)
        else:
            return base_interval
    
    async def get_metrics_history(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get metrics history"""
        
        async with self._lock:
            history = list(self._metrics_history)[-limit:]
        
        return [
            {
                'timestamp': m.timestamp,
                'api_error_rate': round(m.api_error_rate, 4),
                'avg_latency_ms': round(m.avg_latency_ms, 2),
                'memory_usage_mb': round(m.memory_usage_mb, 2),
                'cpu_usage_percent': round(m.cpu_usage_percent, 2),
                'consecutive_failures': m.consecutive_failures
            }
            for m in history
        ]


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_self_defense: Optional[SelfDefenseSystem] = None


def get_self_defense() -> SelfDefenseSystem:
    """Get or create self defense system singleton"""
    global _self_defense
    if _self_defense is None:
        _self_defense = SelfDefenseSystem()
    return _self_defense
