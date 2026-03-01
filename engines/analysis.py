from .risk import RiskEngine
from .whale import WhaleEngine
from config.settings import strategy

class AnalysisEngine:
    @staticmethod
    def analyze_token(pair_data: dict):
        """
        Orchestrates the analysis pipeline.
        Returns None if filtered out, otherwise returns Analysis Result.
        """
        # 1. Hard Filters (Fast Fail)
        liq = float(pair_data.get('liquidity', {}).get('usd', 0))
        if liq < strategy.filters.get('min_liquidity_usd', 1000):
            return None

        # 2. Detailed Analysis
        risk = RiskEngine.evaluate(pair_data)
        whale = WhaleEngine.analyze(pair_data)
        
        # 3. Authenticity (Simple Wash Trade Check)
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
            "metrics": {
                "buy_sell_ratio": round(buy_sell_ratio, 2),
                "volume_h24": vol_h24
            }
        }
