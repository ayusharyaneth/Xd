class ExitAssistant:
    @staticmethod
    def check_exit_conditions(pair_data: dict) -> dict:
        price_change = pair_data.get("priceChange", {}).get("h1", 0)
        if price_change < -30:
            return {"should_exit": True, "reason": "Price dropped > 30% in 1h"}
        return {"should_exit": False, "reason": ""}
