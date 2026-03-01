class RugProbabilityEngine:
    def calculate(self, risk_score, authenticity_score):
        # Synthetic probability
        base_prob = risk_score * 0.7 + (100 - authenticity_score) * 0.3
        return min(99.9, base_prob)
