class RugProbabilityEstimator:
    @staticmethod
    def estimate(risk, auth, dev, cluster) -> float:
        prob = (100 - risk['risk_score']) * 0.4 + (100 - auth) * 0.2 + cluster * 0.4
        return min(100.0, max(0.0, prob))
