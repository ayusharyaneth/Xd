class AuthenticityEngine:
    @staticmethod
    def evaluate(pair_data: dict) -> float:
        txns = pair_data.get("txns", {}).get("h24", {})
        buys = txns.get("buys", 0)
        sells = txns.get("sells", 0)
        total_tx = buys + sells
        vol = pair_data.get("volume", {}).get("h24", 0)
        
        if total_tx == 0: return 0.0
        avg_tx_size = vol / total_tx
        
        # High score if avg tx size is organic (e.g., between 50 and 500 USD)
        if 50 <= avg_tx_size <= 500:
            return 90.0
        return 40.0
