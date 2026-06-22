import os
import sys
import unittest


BENCHMARK_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmark")
sys.path.insert(0, os.path.abspath(BENCHMARK_DIR))

from metrics.latency_tracker import LatencyTracker
from scheduler.realistic_scheduler import RealisticScheduler


class LatencyAndSchedulerTest(unittest.TestCase):
    def test_latency_tracker_rejects_non_finite_values(self):
        tracker = LatencyTracker()

        self.assertFalse(tracker.record(float("inf"), 0.1))
        self.assertFalse(tracker.record(0.1, float("nan")))
        self.assertEqual(tracker.get_ttft_window(), [])
        self.assertEqual(tracker.get_tpot_window(), [])

    def test_realistic_scheduler_counts_failures_without_recording_latency(self):
        tracker = LatencyTracker()
        scheduler = RealisticScheduler(
            latency_tracker=tracker,
            inference_fn=lambda prompt, max_tokens=None: (float("inf"), float("inf")),
            max_workers=1,
            speed_factor=1000.0,
            failure_rate_threshold=0.5,
            min_requests_for_circuit_break=1,
        )

        scheduler.start([
            {"timestamp": 0.0, "user_id": 1, "request": "hello"},
            {"timestamp": 0.001, "user_id": 1, "request": "world"},
        ])

        self.assertEqual(tracker.get_ttft_window(), [])
        self.assertEqual(tracker.get_tpot_window(), [])
        self.assertGreaterEqual(scheduler.get_failure_rate(), 0.5)


if __name__ == "__main__":
    unittest.main()
