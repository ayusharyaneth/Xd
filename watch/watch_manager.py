import time
from typing import Dict

class WatchManager:
    def __init__(self):
        self.watched_tokens: Dict[str, dict] = {} # address -> data

    def add_watch(self, token_address, chat_id, entry_price):
        self.watched_tokens[token_address] = {
            "chat_id": chat_id,
            "entry_price": entry_price,
            "start_time": time.time(),
            "active": True
        }

    def get_active_watches(self):
        return [k for k, v in self.watched_tokens.items() if v['active']]

    def remove_watch(self, token_address):
        if token_address in self.watched_tokens:
            del self.watched_tokens[token_address]
            
    def get_watch_data(self, token_address):
        return self.watched_tokens.get(token_address)

watch_manager = WatchManager()
