import numpy as np

class SLAEngine:

    def __init__(self, ttft_limit, tpot_limit, min_samples=1):
        self.ttft_limit = ttft_limit
        self.tpot_limit = tpot_limit
        self.min_samples = min_samples

    def check(self, ttft_values, tpot_values):
        ttft_values = self._finite_values(ttft_values)
        tpot_values = self._finite_values(tpot_values)
        if len(ttft_values) < self.min_samples or len(tpot_values) < self.min_samples:
            return "INSUFFICIENT_DATA"

        p99_ttft = np.percentile(ttft_values, 99)
        p90_tpot = np.percentile(tpot_values, 90)

        if p99_ttft > self.ttft_limit or p90_tpot > self.tpot_limit:
            return "VIOLATED"

        warning_ttft_threshold = self.ttft_limit * 0.9
        warning_tpot_threshold = self.tpot_limit * 0.9
        if p99_ttft > warning_ttft_threshold or p90_tpot > warning_tpot_threshold:
            return "WARNING"

        return "SAFE"

    @staticmethod
    def _finite_values(values):
        return [value for value in values if np.isfinite(value)]
