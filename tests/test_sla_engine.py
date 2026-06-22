import os
import sys
import unittest


BENCHMARK_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmark")
sys.path.insert(0, os.path.abspath(BENCHMARK_DIR))

from controller.sla_engine import SLAEngine


class SLAEngineTest(unittest.TestCase):
    def test_empty_windows_are_insufficient(self):
        engine = SLAEngine(ttft_limit=1.0, tpot_limit=0.1, min_samples=1)

        self.assertEqual(engine.check([], []), "INSUFFICIENT_DATA")

    def test_non_finite_values_are_ignored_for_sample_count(self):
        engine = SLAEngine(ttft_limit=1.0, tpot_limit=0.1, min_samples=2)

        state = engine.check([0.2, float("inf")], [0.03, float("nan")])

        self.assertEqual(state, "INSUFFICIENT_DATA")

    def test_warning_is_distinct_from_safe(self):
        engine = SLAEngine(ttft_limit=1.0, tpot_limit=0.1, min_samples=3)

        state = engine.check([0.91, 0.92, 0.93], [0.02, 0.03, 0.04])

        self.assertEqual(state, "WARNING")

    def test_safe_when_within_thresholds(self):
        engine = SLAEngine(ttft_limit=1.0, tpot_limit=0.1, min_samples=3)

        state = engine.check([0.2, 0.3, 0.4], [0.02, 0.03, 0.04])

        self.assertEqual(state, "SAFE")


if __name__ == "__main__":
    unittest.main()
