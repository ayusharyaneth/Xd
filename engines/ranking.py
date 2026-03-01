class RankingEngine:
    def rank(self, analyzed_tokens):
        # Sort tokens by Buy Quality and low Risk
        return sorted(analyzed_tokens, key=lambda x: x['scores']['quality'], reverse=True)
