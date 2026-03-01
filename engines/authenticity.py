class AuthenticityEngine:
    def analyze(self, pair_data):
        # Logic: High volume but low distinct txns = Wash trading
        vol_h24 = float(pair_data.get('volume', {}).get('h24', 0))
        txns = pair_data.get('txns', {}).get('h24', {})
        total_tx = txns.get('buys', 0) + txns.get('sells', 0)
        
        if total_tx == 0: return 0.0
        
        avg_tx_size = vol_h24 / total_tx
        # Arbitrary authenticity score
        score = 100
        if avg_tx_size > 5000 and total_tx < 50: # Few big trades
            score -= 40
        return score
