import psutil
import time

class SystemHealth:
    def get_metrics(self):
        return {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "uptime": int(time.time() - psutil.boot_time())
        }
