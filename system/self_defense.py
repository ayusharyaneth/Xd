from system.health import health_monitor
from utils.logger import logger

class SelfDefenseMechanism:
    def __init__(self):
        self.safe_mode_active = False

    def check_and_activate(self) -> bool:
        health = health_monitor.get_system_health()
        if not health["healthy"] and not self.safe_mode_active:
            self.safe_mode_active = True
            logger.warning(f"SAFE MODE ACTIVATED. Metrics: {health}")
            return True
        elif health["healthy"] and self.safe_mode_active:
            self.safe_mode_active = False
            logger.info("System recovered. SAFE MODE DEACTIVATED.")
        return False

    def is_safe_mode(self):
        return self.safe_mode_active

self_defense = SelfDefenseMechanism()
