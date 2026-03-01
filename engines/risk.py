from config.settings import strategy

class RiskEngine:
    @staticmethod
    def evaluate(pair_data: dict) -> dict:
        """
        Calculates a risk score (0-100). Higher is riskier.
        """
        score = 0
        reasons = []

        liquidity = float(pair_data.get('liquidity', {}).get('usd', 0))
        fdv = float(pair_data.get('fdv', 0))
        
        # 1. Liquidity Checks
        if liquidity < strategy.filters.get('min_liquidity_usd', 1000):
            score += 40
            reasons.append("Low Liquidity")
            
        # 2. FDV Checks
        if fdv > strategy.filters.get('max_fdv', 5000000):
            score += 20
            reasons.append("High FDV (Potential Scam)")

        # 3. Liquidity/FDV Ratio (Rug Pull Probability)
        # Healthy tokens usually have Liq > 10% of FDV
        if fdv > 0:
            ratio = liquidity / fdv
            if ratio < 0.05:
                score += 30
                reasons.append("Low Liq/FDV Ratio")
        
        # 4. Socials
        if not pair_data.get('info', {}).get('socials'):
            score += 15
            reasons.append("No Socials")

        return {
            "score": min(100, score),
            "reasons": reasons,
            "is_safe": score < strategy.thresholds.get('risk_alert_level', 70)
        }
