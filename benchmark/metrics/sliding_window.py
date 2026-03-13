# 指标监控：实现滑动窗口统计

# 维护：
# 最近60秒请求

# 用于计算：
# P99 TTFT
# P90 TPOT

# 数据结构：
# deque
# heap

import time
from collections import deque

class SlidingWindow:

    def __init__(self, window_size=60):

        self.window_size = window_size
        self.data = deque()

    def add(self, value):

        now = time.time()

        self.data.append((now, value))

        while self.data and now - self.data[0][0] > self.window_size:

            self.data.popleft()

    def values(self):

        return [v for _, v in self.data]