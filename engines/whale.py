from config.settings import settings

class WhaleEngine:
    @staticmethod
    def detect(pair_data: dict) -> dict:
        # In reality, parse recent trades. Using heuristic for now.
        vol = pair_data.get("volume", {}).get("h1", 0)
        whale_present = vol > settings.MIN_WHALE_TRADE * 5
        return {"whale_detected": whale_present, "largest_trade_usd": vol * 0.1}
