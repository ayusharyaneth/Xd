from config.settings import settings

class RegimeEngine:
    def __init__(self):
        self.history = []

    def update(self, total_volume):
        self.history.append(total_volume)
        if len(self.history) > 50: self.history.pop(0)

    def get_status(self):
        if not self.history: return "NEUTRAL"
        avg_vol = sum(self.history) / len(self.history)
        if avg_vol > settings.regime.get('bull_volume_threshold', 1000000):
            return "BULL"
        if avg_vol < settings.regime.get('bear_volume_threshold', 100000):
            return "BEAR"
        return "NEUTRAL"
