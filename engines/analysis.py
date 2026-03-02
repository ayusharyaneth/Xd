from .risk import RiskEngine
from .whale import WhaleEngine
from config.settings import strategy, settings
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
        
        # --- 0. CHAIN VALIDATION ---
        chain_id = pair_data.get('chainId', '').lower()
        if chain_id != settings.TARGET_CHAIN.lower():
            return None

        # --- 1. DATA EXTRACTION & VALIDATION ---
        
        # Liquidity: DexScreener field: liquidity.usd
        liq_raw = pair_data.get('liquidity', {}).get('usd', 0)
        if liq_raw is None: liq_raw = 0
        liq = float(liq_raw)

        # Volume: DexScreener field: volume.h1
        vol_h1_raw = pair_data.get('volume', {}).get('h1', 0)
        if vol_h1_raw is None: vol_h1_raw = 0
        vol_h1 = float(vol_h1_raw)
        
        # FDV: DexScreener field: fdv
        fdv_raw = pair_data.get('fdv', 0)
        if fdv_raw is None: fdv_raw = 0
        fdv = float(fdv_raw)

        # --- 2. HARD FILTERS (The Gatekeeper) ---
        # All filters apply AND logic. Any failure = Drop.
        
        # A. Liquidity Filter
        min_liq = strategy.filters.get('min_liquidity_usd', 1000)
        if liq < min_liq:
            log.debug(f"DROP [{token_symbol}]: Liq ${liq:,.0f} < Min ${min_liq:,.0f}")
            return None

        # B. Volume Filter (H1)
        min_vol = strategy.filters.get('min_volume_h1', 0)
        if vol_h1 < min_vol:
            log.debug(f"DROP [{token_symbol}]: Vol H1 ${vol_h1:,.0f} < Min ${min_vol:,.0f}")
            return None

        # C. FDV/Market Cap Filter
        max_fdv = strategy.filters.get('max_fdv', 0)
        if max_fdv > 0 and fdv > max_fdv:
             log.debug(f"DROP [{token_symbol}]: FDV ${fdv:,.0f} > Max ${max_fdv:,.0f}")
             return None
             
        min_fdv = strategy.filters.get('min_fdv', 0)
        if min_fdv > 0 and fdv < min_fdv:
             log.debug(f"DROP [{token_symbol}]: FDV ${fdv:,.0f} < Min ${min_fdv:,.0f}")
             return None

        # D. Age Filter
        # DexScreener field: pairCreatedAt (ms)
        created_at_ms = pair_data.get('pairCreatedAt')
        age_hours = 0
        
        if created_at_ms:
            age_hours = (time.time() * 1000 - created_at_ms) / (1000 * 3600)
            max_age = strategy.filters.get('max_age_hours', 24)
            
            if age_hours > max_age:
                log.debug(f"DROP [{token_symbol}]: Age {age_hours:.1f}h > Max {max_age}h")
                return None
        else:
            # If API doesn't return creation time
            if strategy.thresholds.get('strict_filtering', True):
                log.debug(f"DROP [{token_symbol}]: No creation data (Strict Mode)")
                return None

        # --- 3. Detailed Analysis ---
        risk = RiskEngine.evaluate(pair_data)
        
        if not risk['is_safe']:
            log.debug(f"DROP [{token_symbol}]: Risk Filter ({risk['reasons']})")
            return None

        whale = WhaleEngine.analyze(pair_data)
        
        # --- 4. Metrics Extraction ---
        vol_h24 = float(pair_data.get('volume', {}).get('h24', 0))
        txns = pair_data.get('txns', {}).get('h24', {})
        buys = txns.get('buys', 0)
        sells = txns.get('sells', 0)
        
        buy_sell_ratio = buys / sells if sells > 0 else 100
        price_change_h1 = pair_data.get('priceChange', {}).get('h1', 0)
        
        return {
            "address": addr,
            "baseToken": pair_data.get('baseToken'),
            "priceUsd": pair_data.get('priceUsd'),
            "liquidity": liq,
            "fdv": fdv,
            "risk": risk,
            "whale": whale,
            "age_hours": round(age_hours, 2),
            "metrics": {
                "buy_sell_ratio": round(buy_sell_ratio, 2),
                "volume_h1": vol_h1,
                "volume_h24": vol_h24,
                "price_change_h1": price_change_h1
            }
        }
