class MarketRegimeAnalyzer:
    def __init__(self):
        self.current_regime = "NORMAL"

    def analyze(self, global_metrics: dict) -> str:
        # Logic to determine BULL, BEAR, HIGH_VOLATILITY
        self.current_regime = "NORMAL"
        return self.current_regime

regime_analyzer = MarketRegimeAnalyzer()
