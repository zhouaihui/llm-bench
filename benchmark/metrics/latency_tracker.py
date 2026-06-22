# 指标监控：记录延迟数据

# 收集：
# TTFT
# TPOT
# request latency

# 示例：
# request1
# TTFT = 320ms
# TPOT = 35ms

import numpy as np
from metrics.sliding_window import SlidingWindow


class LatencyTracker:
    def __init__(self, window_seconds=60):
        self.ttft_window = SlidingWindow(window_size=window_seconds)
        self.tpot_window = SlidingWindow(window_size=window_seconds)

    def record(self, ttft, tpot):
        self.ttft_window.add(ttft)
        self.tpot_window.add(tpot)

    def get_ttft_window(self):
        return self.ttft_window.values()

    def get_tpot_window(self):
        return self.tpot_window.values()

    def p99_ttft(self):
        values = self.get_ttft_window()
        return np.percentile(values, 99) if values else 0.0

    def p90_tpot(self):
        values = self.get_tpot_window()
        return np.percentile(values, 90) if values else 0.0

    def clear(self):
        self.ttft_window.clear()
        self.tpot_window.clear()