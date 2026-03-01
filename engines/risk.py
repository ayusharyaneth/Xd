from config.settings import settings

class RiskEngine:
    @staticmethod
    def evaluate(pair_data: dict) -> dict:
        liq = pair_data.get("liquidity", {}).get("usd", 0)
        fdv = pair_data.get("fdv", 0)
        
        passed = liq >= settings.MIN_LIQUIDITY and fdv <= settings.MAX_FDV
        score = 100 if passed else 0
        if fdv > 0:
            score -= (fdv / settings.MAX_FDV) * 50
            
        return {"passed": passed, "risk_score": max(0, min(100, score))}
