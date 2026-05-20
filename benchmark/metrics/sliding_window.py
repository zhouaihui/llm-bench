import time
import threading
from collections import deque


class SlidingWindow:

    def __init__(self, window_size=60):
        self.window_size = window_size
        self.data = deque()
        self._lock = threading.Lock()

    def add(self, value):
        now = time.time()
        with self._lock:
            self.data.append((now, value))
            self._evict_old(now)

    def _evict_old(self, now):
        while self.data and now - self.data[0][0] > self.window_size:
            self.data.popleft()

    def values(self):
        now = time.time()
        with self._lock:
            self._evict_old(now)
            return [v for _, v in self.data]

    def clear(self):
        with self._lock:
            self.data.clear()