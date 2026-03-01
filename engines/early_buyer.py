class EarlyBuyerEngine:
    def track(self, pair_data):
        # Requires tx history. 
        # Simulation: Check price change h1 vs h6
        price_change = float(pair_data.get('priceChange', {}).get('h1', 0))
        if price_change > 500:
            return "Early Buyers up > 500%"
        return "Normal"
