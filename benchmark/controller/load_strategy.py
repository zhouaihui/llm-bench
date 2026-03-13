# 控制层：自动加压策略
#
# 自动加压策略。
#
# 阶段1
# Aggressive Ramp-up
# 快速增加并发。
# 例如：
# +20%

# 阶段2
# Stabilization
# 接近 SLA 边界。
# 进入观察期。

# 阶段3
# Backoff
# 如果 SLA 被违反：
# 降低并发
# 例如：
# concurrency *= 0.8
# 目标：
# 找到稳定满足 SLA 的最大容量

class LoadStrategy:

    def __init__(self):

        self.stage = "RAMP_UP"

    def adjust(self, concurrency, state):

        if self.stage == "RAMP_UP":

            if state == "SAFE":

                return int(concurrency * 1.2)

            if state == "WARNING":

                self.stage = "STABILIZE"

                return concurrency

        elif self.stage == "STABILIZE":

            if state == "VIOLATED":

                self.stage = "BACKOFF"

                return int(concurrency * 0.8)

        return concurrency