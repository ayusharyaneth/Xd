from config.settings import settings

class RiskEngine:
    def calculate_risk(self, pair_data):
        score = 0
        liquidity = float(pair_data.get('liquidity', {}).get('usd', 0))
        fdv = float(pair_data.get('fdv', 0))
        
        # High Risk Conditions
        if liquidity < settings.filters['min_liquidity']: score += 40
        if fdv > settings.filters['max_fdv']: score += 20
        if fdv < settings.filters['min_fdv']: score += 10
        
        # Liquidity to FDV ratio (Rug check)
        if fdv > 0 and (liquidity / fdv) < 0.05:
            score += 30
            
        return min(100, score)
