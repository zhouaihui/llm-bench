import math
import os
import sys
import unittest


BENCHMARK_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmark")
sys.path.insert(0, os.path.abspath(BENCHMARK_DIR))

from inference.real_inference import create_inference
from utils.config_loader import validate_configs


class ConfigAndFakeInferenceTest(unittest.TestCase):
    def test_validate_configs_rejects_bad_pressure_range(self):
        sla_config = {"ttft_p99": 1.0, "tpot_p90": 0.1}
        workload_config = {
            "schedule_mode": "realistic",
            "inference_type": "fake",
            "max_users": 8,
            "pressure": {
                "min_rps": 5.0,
                "max_rps": 1.0,
                "rps_precision": 0.1,
            },
        }

        with self.assertRaises(ValueError):
            validate_configs(sla_config, workload_config)

    def test_fake_inference_smoke(self):
        inference_fn = create_inference("fake")

        ttft, tpot = inference_fn("hello", concurrency_factor=1.0, max_tokens=2)

        self.assertTrue(math.isfinite(ttft))
        self.assertTrue(math.isfinite(tpot))
        self.assertGreater(ttft, 0)
        self.assertGreater(tpot, 0)


if __name__ == "__main__":
    unittest.main()
