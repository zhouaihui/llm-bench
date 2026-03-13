# 指标监控：记录延迟数据

# 收集：
# TTFT
# TPOT
# request latency

# 示例：
# request1
# TTFT = 320ms
# TPOT = 35ms

# 指标监控：记录延迟数据
# 收集：
# TTFT
# TPOT
# request latency

# metrics/latency_tracker.py
import time
from collections import deque
import numpy as np

class LatencyTracker:
    def __init__(self, window_seconds=60):
        self.window_seconds = window_seconds
        self.records = deque()  # 存储形式：[(timestamp, ttft, tpot), ...]

    def record(self, ttft, tpot):
        now = time.time()
        self.records.append((now, ttft, tpot))
        self._evict_old(now)

    def _evict_old(self, now):
        while self.records and self.records[0][0] < now - self.window_seconds:
            self.records.popleft()

    def get_ttft_window(self):
        now = time.time()
        self._evict_old(now)
        return [r[1] for r in self.records]

    def get_tpot_window(self):
        now = time.time()
        self._evict_old(now)
        return [r[2] for r in self.records]

    def p99_ttft(self):
        ttft_window = self.get_ttft_window()
        return np.percentile(ttft_window, 99) if ttft_window else 0.0

    def p90_tpot(self):
        tpot_window = self.get_tpot_window()
        return np.percentile(tpot_window, 90) if tpot_window else 0.0