class ExitEngine:
    def should_exit(self, current_price, entry_price, config):
        pnl = ((current_price - entry_price) / entry_price) * 100
        if pnl >= config.get('profit_trigger_percent', 100):
            return True, "Take Profit"
        if pnl <= config.get('stop_loss_percent', -30):
            return True, "Stop Loss"
        return False, None
