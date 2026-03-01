from config.settings import settings

class WhaleEngine:
    def detect(self, pair_data):
        # Simulating whale detection based on volume vs liquidity
        liquidity = float(pair_data.get('liquidity', {}).get('usd', 1))
        vol_h1 = float(pair_data.get('volume', {}).get('h1', 0))
        
        # If hourly volume > 50% of liquidity, likely whale activity
        if vol_h1 > (liquidity * 0.5):
            return True, "High Volume/Liq Ratio"
        return False, None
