import time
from collections import deque

class MetricsTracker:
    def __init__(self):
        self.api_calls = deque(maxlen=1000)
        self.errors = deque(maxlen=1000)
        self.latencies = deque(maxlen=100)

    def start_timer(self):
        return time.time()

    def stop_timer(self, start_time):
        return (time.time() - start_time) * 1000

    def record_api_call(self, endpoint: str, latency_ms: float):
        self.api_calls.append(time.time())
        self.latencies.append(latency_ms)
        if "error" in endpoint:
            self.errors.append(time.time())

    def get_error_rate(self) -> float:
        if not self.api_calls:
            return 0.0
        return len(self.errors) / len(self.api_calls)

    def get_avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

metrics = MetricsTracker()
