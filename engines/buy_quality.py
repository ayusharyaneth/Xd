class BuyQualityEngine:
    def evaluate(self, pair_data):
        txns = pair_data.get('txns', {}).get('h24', {})
        buys = txns.get('buys', 0)
        sells = txns.get('sells', 0)
        if sells == 0: return 100
        ratio = buys / sells
        return min(100, ratio * 20)
