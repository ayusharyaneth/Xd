import psutil
from config.settings import strategy
from utils.logger import log

class SystemHealth:
    _safe_mode = False

    @classmethod
    def check(cls):
        """
        Returns True if system is stressed (Safe Mode), False otherwise.
        """
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        
        threshold = strategy.thresholds.get('safe_mode_cpu', 85)

        if cpu > threshold or mem > threshold:
            if not cls._safe_mode:
                log.warning(f"⚠️ HIGH LOAD (CPU {cpu}%). Entering Safe Mode.")
                cls._safe_mode = True
            return True
        
        if cls._safe_mode and cpu < (threshold - 10):
            log.info("✅ Load normalized. Exiting Safe Mode.")
            cls._safe_mode = False
            
        return cls._safe_mode
