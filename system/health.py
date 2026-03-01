# ============================================================
# HEALTH CHECK SYSTEM
# ============================================================

import asyncio
import psutil
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp


logger = get_logger("health")


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    check_name: str
    status: str  # 'healthy', 'warning', 'critical'
    message: str
    response_time_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: int = field(default_factory=get_timestamp)


class HealthChecker:
    """System health monitoring"""
    
    def __init__(self):
        self.config = get_config()
        self.health_config = self.config.strategy.health_check
        self._check_results: List[HealthCheckResult] = []
        self._last_check: Optional[int] = None
        self._lock = asyncio.Lock()
    
    async def run_health_checks(
        self,
        dexscreener_client=None,
        signal_bot=None,
        alert_bot=None
    ) -> Dict[str, Any]:
        """Run all health checks"""
        
        if not self.health_config.enabled:
            return {'enabled': False}
        
        results = []
        start_time = time.time()
        
        # API connectivity check
        if self.health_config.checks.api_connectivity and dexscreener_client:
            result = await self._check_api_connectivity(dexscreener_client)
            results.append(result)
        
        # Bot responsiveness check
        if self.health_config.checks.bot_responsiveness:
            if signal_bot:
                result = await self._check_bot_responsiveness(signal_bot, "signal")
                results.append(result)
            if alert_bot:
                result = await self._check_bot_responsiveness(alert_bot, "alert")
                results.append(result)
        
        # Memory usage check
        if self.health_config.checks.memory_usage:
            result = self._check_memory_usage()
            results.append(result)
        
        # Disk space check
        if self.health_config.checks.disk_space:
            result = self._check_disk_space()
            results.append(result)
        
        # Store results
        async with self._lock:
            self._check_results.extend(results)
            self._last_check = get_timestamp()
            
            # Keep only recent results
            cutoff = get_timestamp() - 86400
            self._check_results = [
                r for r in self._check_results
                if r.timestamp > cutoff
            ]
        
        # Calculate overall status
        overall_status = self._calculate_overall_status(results)
        
        total_time = (time.time() - start_time) * 1000
        
        return {
            'status': overall_status,
            'checks_run': len(results),
            'total_time_ms': round(total_time, 2),
            'timestamp': get_timestamp(),
            'checks': [
                {
                    'name': r.check_name,
                    'status': r.status,
                    'message': r.message,
                    'response_time_ms': r.response_time_ms
                }
                for r in results
            ]
        }
    
    async def _check_api_connectivity(
        self,
        dexscreener_client
    ) -> HealthCheckResult:
        """Check DexScreener API connectivity"""
        
        start_time = time.time()
        
        try:
            # Try to get stats which makes a lightweight call
            stats = dexscreener_client.get_stats()
            
            response_time = (time.time() - start_time) * 1000
            
            error_rate = stats.get('error_rate', 0)
            
            if error_rate > 0.2:
                status = 'warning'
                message = f"High API error rate: {error_rate:.1%}"
            else:
                status = 'healthy'
                message = "API connectivity OK"
            
            return HealthCheckResult(
                check_name='api_connectivity',
                status=status,
                message=message,
                response_time_ms=round(response_time, 2),
                details={
                    'error_rate': error_rate,
                    'total_requests': stats.get('total_requests', 0)
                }
            )
        
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                check_name='api_connectivity',
                status='critical',
                message=f"API check failed: {str(e)}",
                response_time_ms=round(response_time, 2),
                details={'error': str(e)}
            )
    
    async def _check_bot_responsiveness(
        self,
        bot,
        bot_type: str
    ) -> HealthCheckResult:
        """Check bot responsiveness"""
        
        start_time = time.time()
        
        try:
            # Check if bot is running
            if hasattr(bot, 'is_running') and bot.is_running:
                status = 'healthy'
                message = f"{bot_type.capitalize()} bot is responsive"
            elif hasattr(bot, 'application') and bot.application:
                status = 'healthy'
                message = f"{bot_type.capitalize()} bot application active"
            else:
                status = 'warning'
                message = f"{bot_type.capitalize()} bot status unclear"
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                check_name=f'{bot_type}_bot',
                status=status,
                message=message,
                response_time_ms=round(response_time, 2)
            )
        
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                check_name=f'{bot_type}_bot',
                status='critical',
                message=f"Bot check failed: {str(e)}",
                response_time_ms=round(response_time, 2),
                details={'error': str(e)}
            )
    
    def _check_memory_usage(self) -> HealthCheckResult:
        """Check system memory usage"""
        
        start_time = time.time()
        
        try:
            memory = psutil.virtual_memory()
            used_percent = memory.percent
            used_mb = memory.used / (1024 * 1024)
            
            thresholds = self.health_config.thresholds
            
            if used_percent >= thresholds.max_memory_percent:
                status = 'critical'
                message = f"Memory usage critical: {used_percent:.1f}%"
            elif used_percent >= thresholds.max_memory_percent * 0.8:
                status = 'warning'
                message = f"Memory usage high: {used_percent:.1f}%"
            else:
                status = 'healthy'
                message = f"Memory usage OK: {used_percent:.1f}%"
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                check_name='memory_usage',
                status=status,
                message=message,
                response_time_ms=round(response_time, 2),
                details={
                    'used_percent': used_percent,
                    'used_mb': round(used_mb, 2),
                    'available_mb': round(memory.available / (1024 * 1024), 2)
                }
            )
        
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                check_name='memory_usage',
                status='critical',
                message=f"Memory check failed: {str(e)}",
                response_time_ms=round(response_time, 2),
                details={'error': str(e)}
            )
    
    def _check_disk_space(self) -> HealthCheckResult:
        """Check disk space usage"""
        
        start_time = time.time()
        
        try:
            disk = psutil.disk_usage('/')
            used_gb = disk.used / (1024 * 1024 * 1024)
            free_gb = disk.free / (1024 * 1024 * 1024)
            
            thresholds = self.health_config.thresholds
            
            if free_gb < thresholds.min_disk_space_gb:
                status = 'critical'
                message = f"Disk space low: {free_gb:.1f}GB free"
            elif free_gb < thresholds.min_disk_space_gb * 2:
                status = 'warning'
                message = f"Disk space getting low: {free_gb:.1f}GB free"
            else:
                status = 'healthy'
                message = f"Disk space OK: {free_gb:.1f}GB free"
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                check_name='disk_space',
                status=status,
                message=message,
                response_time_ms=round(response_time, 2),
                details={
                    'used_gb': round(used_gb, 2),
                    'free_gb': round(free_gb, 2),
                    'total_gb': round(disk.total / (1024 * 1024 * 1024), 2)
                }
            )
        
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                check_name='disk_space',
                status='critical',
                message=f"Disk check failed: {str(e)}",
                response_time_ms=round(response_time, 2),
                details={'error': str(e)}
            )
    
    def _calculate_overall_status(
        self,
        results: List[HealthCheckResult]
    ) -> str:
        """Calculate overall health status"""
        
        if not results:
            return 'unknown'
        
        critical_count = sum(1 for r in results if r.status == 'critical')
        warning_count = sum(1 for r in results if r.status == 'warning')
        
        if critical_count > 0:
            return 'critical'
        elif warning_count > 0:
            return 'warning'
        else:
            return 'healthy'
    
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get health check summary"""
        
        async with self._lock:
            results = self._check_results[-10:]  # Last 10 checks
            last_check = self._last_check
        
        if not results:
            return {
                'status': 'unknown',
                'last_check': None,
                'message': 'No health checks performed yet'
            }
        
        # Count by status
        status_counts = {}
        for r in results:
            status_counts[r.status] = status_counts.get(r.status, 0) + 1
        
        # Average response times
        avg_response = sum(r.response_time_ms for r in results) / len(results)
        
        return {
            'status': 'healthy' if status_counts.get('critical', 0) == 0 else 'critical',
            'last_check': last_check,
            'checks_count': len(results),
            'status_breakdown': status_counts,
            'average_response_ms': round(avg_response, 2),
            'time_since_last_check_seconds': get_timestamp() - last_check if last_check else None
        }
    
    async def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed health status"""
        
        async with self._lock:
            results = self._check_results[-50:]  # Last 50 results
        
        # Group by check name
        by_check = {}
        for r in results:
            if r.check_name not in by_check:
                by_check[r.check_name] = []
            by_check[r.check_name].append(r)
        
        detailed = {}
        for check_name, check_results in by_check.items():
            latest = check_results[-1]
            
            # Calculate trend
            if len(check_results) >= 3:
                recent_statuses = [r.status for r in check_results[-3:]]
                if all(s == 'healthy' for s in recent_statuses):
                    trend = 'stable_healthy'
                elif all(s == 'critical' for s in recent_statuses):
                    trend = 'stable_critical'
                elif recent_statuses[-1] != recent_statuses[0]:
                    trend = 'degrading' if recent_statuses[-1] == 'critical' else 'improving'
                else:
                    trend = 'stable'
            else:
                trend = 'insufficient_data'
            
            detailed[check_name] = {
                'latest_status': latest.status,
                'latest_message': latest.message,
                'response_time_ms': latest.response_time_ms,
                'trend': trend,
                'check_count': len(check_results)
            }
        
        return detailed


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create health checker singleton"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
