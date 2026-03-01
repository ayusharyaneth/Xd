class BuyQualityEngine:
    @staticmethod
    def evaluate(pair_data: dict) -> float:
        txns = pair_data.get("txns", {}).get("h24", {})
        buys = txns.get("buys", 1)
        sells = txns.get("sells", 1)
        ratio = buys / max(sells, 1)
        return min(100.0, ratio * 20)
