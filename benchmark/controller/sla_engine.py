# 控制层：SLA监控引擎
#
# 计算 P99 TTFT
# 计算 P90 TPOT
# 判断SLA是否满足

# 内部维护：滑动窗口

# 例如：最近60秒请求

# 输出状态：
# SAFE
# WARNING
# VIOLATED

import numpy as np

class SLAEngine:

    def __init__(self, ttft_limit, tpot_limit):

        self.ttft_limit = ttft_limit
        self.tpot_limit = tpot_limit

    def check(self, ttft_values, tpot_values):

        p99 = np.percentile(ttft_values, 99)

        p90 = np.percentile(tpot_values, 90)

        if p99 > self.ttft_limit:

            return "VIOLATED"

        if p90 > self.tpot_limit:

            return "WARNING"

        return "SAFE"