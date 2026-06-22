"""Run llm-bench from the repository root."""
import os
import sys


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BENCHMARK_DIR = os.path.join(ROOT_DIR, "benchmark")
if BENCHMARK_DIR not in sys.path:
    sys.path.insert(0, BENCHMARK_DIR)

from main import main  # noqa: E402


if __name__ == "__main__":
    main()
