from config.settings import settings
import psutil
from loguru import logger

class SelfDefense:
    def __init__(self):
        self.safe_mode = False

    def check(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        
        limit_cpu = settings.thresholds.get('safe_mode_cpu_percent', 90)
        limit_mem = settings.thresholds.get('safe_mode_mem_percent', 90)

        if cpu > limit_cpu or mem > limit_mem:
            if not self.safe_mode:
                logger.warning(f"SELF DEFENSE ACTIVATED: CPU {cpu}%, MEM {mem}%")
                self.safe_mode = True
            return True
        
        if self.safe_mode and cpu < (limit_cpu - 10):
            self.safe_mode = False
            logger.info("Self Defense Deactivated")
            
        return self.safe_mode
