from .risk import RiskEngine
from .whale import WhaleEngine
from config.settings import strategy
from utils.logger import log
import time

class AnalysisEngine:
    @staticmethod
    def analyze_token(pair_data: dict):
        """
        Orchestrates the analysis pipeline.
        Returns None if filtered out, otherwise returns Analysis Result.
        """
        # --- 1. HARD FILTERS (The Gatekeeper) ---
        
        # A. Liquidity Filter
        liq = float(pair_data.get('liquidity', {}).get('usd', 0))
        min_liq = strategy.filters.get('min_liquidity_usd', 1000)
        if liq < min_liq:
            return None

        # B. Age Filter (Crucial for preventing flooding)
        created_at_ms = pair_data.get('pairCreatedAt', 0)
        if created_at_ms:
            # Convert ms to hours
            age_hours = (time.time() * 1000 - created_at_ms) / (1000 * 3600)
            max_age = strategy.filters.get('max_age_hours', 24)
            
            if age_hours > max_age:
                # Token is too old, ignore it
                return None
        else:
            # If no creation time, assume old and skip to be safe
            return None

        # --- 2. Detailed Analysis ---
        risk = RiskEngine.evaluate(pair_data)
        
        # If Risk Engine flags it as unsafe immediately, return early
        if not risk['is_safe']:
            return None

        whale = WhaleEngine.analyze(pair_data)
        
        # --- 3. Authenticity (Simple Wash Trade Check) ---
        vol_h24 = float(pair_data.get('volume', {}).get('h24', 0))
        txns = pair_data.get('txns', {}).get('h24', {})
        buys = txns.get('buys', 0)
        sells = txns.get('sells', 0)
        
        buy_sell_ratio = buys / sells if sells > 0 else 100
        
        return {
            "address": pair_data.get('pairAddress'),
            "baseToken": pair_data.get('baseToken'),
            "priceUsd": pair_data.get('priceUsd'),
            "liquidity": liq,
            "risk": risk,
            "whale": whale,
            "age_hours": round(age_hours, 2),
            "metrics": {
                "buy_sell_ratio": round(buy_sell_ratio, 2),
                "volume_h24": vol_h24
            }
        }
