# ============================================================
# SYSTEM METRICS COLLECTOR
# ============================================================

import asyncio
import psutil
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from datetime import datetime

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, format_duration


logger = get_logger("metrics")


@dataclass
class MetricPoint:
    """Single metric data point"""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: int = field(default_factory=get_timestamp)


class MetricsCollector:
    """Collect and store system metrics"""
    
    def __init__(self):
        self.config = get_config()
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._system_metrics: deque = deque(maxlen=100)
        self._start_time = get_timestamp()
        self._lock = asyncio.Lock()
    
    async def record_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ):
        """Record a metric value"""
        
        metric = MetricPoint(
            name=name,
            value=value,
            labels=labels or {}
        )
        
        async with self._lock:
            key = f"{name}:{str(labels)}"
            self._metrics[key].append(metric)
    
    async def increment_counter(
        self,
        name: str,
        value: int = 1
    ):
        """Increment a counter metric"""
        async with self._lock:
            self._counters[name] += value
    
    async def set_gauge(
        self,
        name: str,
        value: float
    ):
        """Set a gauge metric"""
        async with self._lock:
            self._gauges[name] = value
    
    async def collect_system_metrics(self):
        """Collect system-level metrics"""
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            await self.set_gauge('system_cpu_percent', cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            await self.set_gauge('system_memory_percent', memory.percent)
            await self.set_gauge('system_memory_used_mb', memory.used / (1024 * 1024))
            
            # Disk usage
            disk = psutil.disk_usage('/')
            await self.set_gauge('system_disk_percent', (disk.used / disk.total) * 100)
            
            # Network I/O
            net_io = psutil.net_io_counters()
            await self.set_gauge('system_net_sent_mb', net_io.bytes_sent / (1024 * 1024))
            await self.set_gauge('system_net_recv_mb', net_io.bytes_recv / (1024 * 1024))
            
            # Process info
            process = psutil.Process()
            await self.set_gauge('process_memory_mb', process.memory_info().rss / (1024 * 1024))
            await self.set_gauge('process_cpu_percent', process.cpu_percent())
            await self.set_gauge('process_threads', process.num_threads())
            
            # Store snapshot
            snapshot = {
                'timestamp': get_timestamp(),
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': (disk.used / disk.total) * 100
            }
            
            async with self._lock:
                self._system_metrics.append(snapshot)
        
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    async def get_metric_stats(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        minutes: int = 60
    ) -> Dict[str, Any]:
        """Get statistics for a metric"""
        
        cutoff = get_timestamp() - (minutes * 60)
        
        async with self._lock:
            key = f"{name}:{str(labels)}"
            metrics = [
                m for m in self._metrics.get(key, [])
                if m.timestamp > cutoff
            ]
        
        if not metrics:
            return {'error': 'No data for metric'}
        
        values = [m.value for m in metrics]
        
        return {
            'name': name,
            'labels': labels,
            'count': len(values),
            'latest': values[-1],
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values),
            'first_timestamp': metrics[0].timestamp,
            'last_timestamp': metrics[-1].timestamp
        }
    
    async def get_counter_value(self, name: str) -> int:
        """Get current counter value"""
        async with self._lock:
            return self._counters.get(name, 0)
    
    async def get_gauge_value(self, name: str) -> Optional[float]:
        """Get current gauge value"""
        async with self._lock:
            return self._gauges.get(name)
    
    async def get_all_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics"""
        
        async with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            system = list(self._system_metrics)[-10:]
        
        uptime = get_timestamp() - self._start_time
        
        return {
            'uptime_seconds': uptime,
            'uptime_formatted': format_duration(uptime),
            'counters': counters,
            'gauges': {k: round(v, 4) for k, v in gauges.items()},
            'system_snapshots': system,
            'tracked_metrics': len(self._metrics)
        }
    
    async def get_engine_stats(self) -> Dict[str, Any]:
        """Get statistics for all engines"""
        
        async with self._lock:
            counters = dict(self._counters)
        
        # Group by engine
        engine_stats = defaultdict(lambda: {
            'alerts_generated': 0,
            'tokens_processed': 0,
            'errors': 0
        })
        
        for key, value in counters.items():
            if '_' in key:
                engine = key.split('_')[0]
                metric_type = '_'.join(key.split('_')[1:])
                
                if 'alert' in metric_type:
                    engine_stats[engine]['alerts_generated'] += value
                elif 'token' in metric_type or 'processed' in metric_type:
                    engine_stats[engine]['tokens_processed'] += value
                elif 'error' in metric_type:
                    engine_stats[engine]['errors'] += value
        
        return dict(engine_stats)
    
    async def reset_counter(self, name: str):
        """Reset a counter to zero"""
        async with self._lock:
            self._counters[name] = 0
    
    async def cleanup_old_data(self, max_age_hours: int = 24):
        """Clean up old metric data"""
        
        cutoff = get_timestamp() - (max_age_hours * 3600)
        
        async with self._lock:
            # Clean old metric points
            for key in list(self._metrics.keys()):
                self._metrics[key] = deque(
                    [m for m in self._metrics[key] if m.timestamp > cutoff],
                    maxlen=1000
                )
                if not self._metrics[key]:
                    del self._metrics[key]
            
            # Clean old system metrics
            self._system_metrics = deque(
                [m for m in self._system_metrics if m['timestamp'] > cutoff],
                maxlen=100
            )


# ============================================================
# PERFORMANCE TRACKER
# ============================================================

class PerformanceTracker:
    """Track performance of various operations"""
    
    def __init__(self):
        self._operation_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._lock = asyncio.Lock()
    
    async def record_operation_time(
        self,
        operation: str,
        duration_ms: float
    ):
        """Record operation execution time"""
        async with self._lock:
            self._operation_times[operation].append({
                'timestamp': get_timestamp(),
                'duration_ms': duration_ms
            })
    
    async def get_performance_stats(
        self,
        operation: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get performance statistics"""
        
        async with self._lock:
            if operation:
                times = list(self._operation_times.get(operation, []))
                return self._calculate_stats(operation, times)
            else:
                return {
                    op: self._calculate_stats(op, list(times))
                    for op, times in self._operation_times.items()
                }
    
    def _calculate_stats(
        self,
        operation: str,
        times: List[Dict]
    ) -> Dict[str, Any]:
        """Calculate statistics for operation times"""
        
        if not times:
            return {'error': 'No data'}
        
        durations = [t['duration_ms'] for t in times]
        
        return {
            'operation': operation,
            'count': len(durations),
            'avg_ms': round(sum(durations) / len(durations), 2),
            'min_ms': round(min(durations), 2),
            'max_ms': round(max(durations), 2),
            'p95_ms': round(sorted(durations)[int(len(durations) * 0.95)], 2) if len(durations) > 20 else None,
            'last_executed': times[-1]['timestamp']
        }


# ============================================================
# SINGLETON INSTANCES
# ============================================================

_metrics_collector: Optional[MetricsCollector] = None
_performance_tracker: Optional[PerformanceTracker] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create metrics collector singleton"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_performance_tracker() -> PerformanceTracker:
    """Get or create performance tracker singleton"""
    global _performance_tracker
    if _performance_tracker is None:
        _performance_tracker = PerformanceTracker()
    return _performance_tracker
