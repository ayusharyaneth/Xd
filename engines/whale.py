from config.settings import strategy

class WhaleEngine:
    @staticmethod
    def analyze(pair_data: dict) -> dict:
        """
        Detects if whales are present based on volume/transaction size.
        """
        detected = False
        details = []
        
        # Analyze h1 volume vs liquidity
        vol_h1 = float(pair_data.get('volume', {}).get('h1', 0))
        liquidity = float(pair_data.get('liquidity', {}).get('usd', 1))
        
        # If hourly volume is 2x liquidity, high volatility/whale action
        if vol_h1 > (liquidity * 2.0):
            detected = True
            details.append("Volume Spike > 2x Liq")

        # High Transaction Count
        txns = pair_data.get('txns', {}).get('h1', {})
        total_tx = txns.get('buys', 0) + txns.get('sells', 0)
        
        if total_tx > 500:
            detected = True
            details.append("High TX Frequency")

        return {
            "detected": detected,
            "details": details
        }
