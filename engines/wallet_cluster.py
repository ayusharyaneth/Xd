from config.settings import settings

class WalletClusterEngine:
    def detect_clusters(self, pair_data):
        # Logic: In a real RPC environment, check block timestamps.
        # Here we simulate a suspicion score based on buy burst.
        txns_h1 = pair_data.get('txns', {}).get('h1', {}).get('buys', 0)
        if txns_h1 > 1000: # Suspiciously high for a new token
            return 80 # High cluster suspicion
        return 10
