# 控制层：自动加压策略
#
# 三阶段策略：RAMP_UP -> STABILIZE -> BACKOFF
# 支持从 BACKOFF 恢复到 STABILIZE，避免死锁在降级状态

class LoadStrategy:

    def __init__(self):
        self.stage = "RAMP_UP"
        self.backoff_count = 0
        self.max_backoff_retries = 3

    def adjust(self, concurrency, state):
        if self.stage == "RAMP_UP":
            if state == "SAFE":
                return int(concurrency * 1.2)
            elif state == "WARNING":
                self.stage = "STABILIZE"
                return concurrency
            elif state == "VIOLATED":
                self.stage = "BACKOFF"
                return int(concurrency * 0.8)

        elif self.stage == "STABILIZE":
            if state == "SAFE":
                self.stage = "RAMP_UP"
                return int(concurrency * 1.1)
            elif state == "VIOLATED":
                self.stage = "BACKOFF"
                self.backoff_count = 0
                return int(concurrency * 0.8)

        elif self.stage == "BACKOFF":
            if state == "SAFE":
                self.backoff_count = 0
                self.stage = "STABILIZE"
                return concurrency
            elif state == "WARNING":
                self.backoff_count = 0
                self.stage = "STABILIZE"
                return concurrency
            else:
                self.backoff_count += 1
                if self.backoff_count >= self.max_backoff_retries:
                    return max(1, int(concurrency * 0.5))
                return max(1, int(concurrency * 0.8))

        return concurrency

    def reset(self):
        self.stage = "RAMP_UP"
        self.backoff_count = 0
