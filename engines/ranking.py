class RankingEngine:
    def __init__(self):
        self.buffer = []

    def add_alert(self, token_data: dict, composite_score: float):
        self.buffer.append({"data": token_data, "score": composite_score})

    def get_top_n(self, n=5):
        sorted_alerts = sorted(self.buffer, key=lambda x: x["score"], reverse=True)
        top = sorted_alerts[:n]
        self.buffer = [] # clear buffer
        return top

ranking_engine = RankingEngine()
