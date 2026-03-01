import psutil
from system.metrics import metrics
from config.settings import settings

class HealthMonitor:
    @staticmethod
    def get_system_health():
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        err_rate = metrics.get_error_rate()
        latency = metrics.get_avg_latency()
        
        is_healthy = (
            mem.percent < settings.MAX_MEMORY_PERCENT and
            err_rate < settings.MAX_ERROR_RATE and
            latency < settings.MAX_LATENCY_MS
        )
        
        return {
            "healthy": is_healthy,
            "memory_percent": mem.percent,
            "cpu_percent": cpu,
            "error_rate": err_rate,
            "avg_latency_ms": latency
        }

health_monitor = HealthMonitor()
