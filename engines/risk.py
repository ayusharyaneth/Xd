from config.settings import strategy
from utils.logger import log

class RiskEngine:
    @staticmethod
    def evaluate(pair_data: dict) -> dict:
        """
        Calculates a risk score (0-100). Higher is riskier.
        Now integrates dynamic weights from strategy.yaml correctly.
        """
        score = 0
        reasons = []
        
        # Load fresh weights
        weights = strategy.weights
        w_liq = weights.get('liquidity_score', 1.0)
        w_vol = weights.get('volume_authenticity', 1.5)
        w_whale = weights.get('whale_presence', 2.0)
        w_dev = weights.get('dev_reputation', 1.0)

        # 1. Liquidity Factor
        liquidity = float(pair_data.get('liquidity', {}).get('usd', 0))
        # Base penalty for low liquidity
        if liquidity < 5000:
            penalty = 40 * w_liq
            score += penalty
            reasons.append(f"Low Liq ({penalty:.1f})")
            
        # 2. FDV / Market Cap Factor
        fdv = float(pair_data.get('fdv', 0))
        if fdv > 5000000:
            penalty = 20 * w_vol # Using volume weight as proxy for hype/valuation risk
            score += penalty
            reasons.append(f"High FDV ({penalty:.1f})")

        # 3. Liquidity/FDV Ratio (Rug Pull Probability)
        if fdv > 0:
            ratio = liquidity / fdv
            if ratio < 0.05:
                penalty = 30 * w_dev # Using dev rep weight as proxy for structure quality
                score += penalty
                reasons.append(f"Low Liq/FDV ({penalty:.1f})")
        
        # 4. Socials (Dev Reputation proxy)
        if not pair_data.get('info', {}).get('socials'):
            penalty = 15 * w_dev
            score += penalty
            reasons.append(f"No Socials ({penalty:.1f})")

        # Normalize score to 0-100 cap
        final_score = min(100, score)
        
        # Debug logging for visibility
        log.debug(
            f"Risk Eval: {pair_data.get('baseToken',{}).get('symbol')} | "
            f"Score: {final_score:.1f} | Weights: L={w_liq} V={w_vol} W={w_whale} D={w_dev}"
        )

        return {
            "score": final_score,
            "reasons": reasons,
            "is_safe": final_score < strategy.thresholds.get('risk_alert_level', 70)
        }
