from config.settings import strategy
from utils.logger import log

class WhaleEngine:
    @staticmethod
    def analyze(pair_data: dict) -> dict:
        """
        Detects if whales are present based on volume/transaction size.
        Integrates weights for sensitivity tuning.
        """
        detected = False
        details = []
        
        # Pull dynamic weight
        w_whale = strategy.weights.get('whale_presence', 2.0)
        
        # Analyze h1 volume vs liquidity
        vol_h1 = float(pair_data.get('volume', {}).get('h1', 0))
        liquidity = float(pair_data.get('liquidity', {}).get('usd', 1))
        
        # Base threshold is 2x liquidity, modified by weight
        # Higher weight = stricter (lower threshold multiplier)
        # If w_whale = 2.0, threshold = 2.0 / 2.0 = 1.0 (More sensitive)
        # If w_whale = 0.5, threshold = 2.0 / 0.5 = 4.0 (Less sensitive)
        
        threshold_mult = 2.0
        if w_whale > 0:
            threshold_mult = 2.0 / w_whale
            
        if vol_h1 > (liquidity * threshold_mult):
            detected = True
            details.append(f"Vol > {threshold_mult:.1f}x Liq")

        # High Transaction Count Check
        txns = pair_data.get('txns', {}).get('h1', {})
        total_tx = txns.get('buys', 0) + txns.get('sells', 0)
        
        if total_tx > 500:
            detected = True
            details.append("High TX Frequency")

        if detected:
            log.debug(f"Whale Detected: {details} (Weight: {w_whale})")

        return {
            "detected": detected,
            "details": details
        }
