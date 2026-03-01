from .risk import RiskEngine
from .whale import WhaleEngine
from config.settings import strategy
from utils.logger import log
import time

class AnalysisEngine:
    @staticmethod
    def analyze_token(pair_data: dict):
        """
        Orchestrates the analysis pipeline with detailed debug logging 
        to diagnose why tokens are being dropped.
        """
        token_symbol = pair_data.get('baseToken', {}).get('symbol', 'UNKNOWN')
        addr = pair_data.get('pairAddress', 'UNKNOWN')

        # --- 1. DATA VALIDITY CHECK ---
        liq_raw = pair_data.get('liquidity', {}).get('usd', 0)
        if liq_raw is None: liq_raw = 0
        liq = float(liq_raw)

        # --- 2. HARD FILTERS (The Gatekeeper) ---
        
        # A. Liquidity Filter
        min_liq = strategy.filters.get('min_liquidity_usd', 1000)
        if liq < min_liq:
            log.debug(f"DROP [{token_symbol}]: Liq ${liq:.0f} < ${min_liq}")
            return None

        # B. Age Filter
        # DexScreener often provides pairCreatedAt in milliseconds
        created_at_ms = pair_data.get('pairCreatedAt')
        age_hours = 0
        
        if created_at_ms:
            age_hours = (time.time() * 1000 - created_at_ms) / (1000 * 3600)
            max_age = strategy.filters.get('max_age_hours', 24)
            
            if age_hours > max_age:
                log.debug(f"DROP [{token_symbol}]: Age {age_hours:.1f}h > {max_age}h")
                return None
        else:
            # If API doesn't return creation time, we can either skip or pass.
            # For safety, strict mode skips.
            if strategy.thresholds.get('strict_filtering', True):
                log.debug(f"DROP [{token_symbol}]: No creation data (Strict Mode)")
                return None

        # --- 3. Detailed Analysis ---
        risk = RiskEngine.evaluate(pair_data)
        
        if not risk['is_safe']:
            log.debug(f"DROP [{token_symbol}]: Risk Filter ({risk['reasons']})")
            return None

        whale = WhaleEngine.analyze(pair_data)
        
        # --- 4. Authenticity ---
        vol_h24 = float(pair_data.get('volume', {}).get('h24', 0))
        txns = pair_data.get('txns', {}).get('h24', {})
        buys = txns.get('buys', 0)
        sells = txns.get('sells', 0)
        
        buy_sell_ratio = buys / sells if sells > 0 else 100
        
        return {
            "address": addr,
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
