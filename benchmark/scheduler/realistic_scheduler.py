"""
真实负载调度器

基于 Kimi Mooncake trace 的 timestamp 控制请求发送时间，
模拟真实的请求到达模式（包含突发流量和空闲期），
替代固定 RPS 的均匀发送方式。

核心区别：
  - ConversationScheduler: 每个用户独立线程，固定 RPS + 指数分布间隔
  - RealisticScheduler: 全局按 trace timestamp 编排，所有请求按真实时间发送
"""

import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.logger import logger


class RealisticScheduler:
    """
    基于 trace timestamp 的真实负载调度器。

    将所有请求按 timestamp 排序后，按真实的时间间隔发送。
    支持时间缩放（speed_factor）来加速或减速回放。
    """

    def __init__(self, latency_tracker, inference_fn,
                 max_workers=64, speed_factor=1.0,
                 failure_rate_threshold=0.5, min_requests_for_circuit_break=20):
        """
        Args:
            latency_tracker: 延迟记录器
            inference_fn: 推理函数，签名 (prompt, max_tokens=None) -> (ttft, tpot)
            max_workers: 最大并发工作线程数
            speed_factor: 时间缩放因子。1.0=原始速度，2.0=两倍速，0.5=半速
            failure_rate_threshold: 失败率熔断阈值（0~1），超过则提前终止
            min_requests_for_circuit_break: 触发熔断检测的最小已完成请求数
        """
        self.latency_tracker = latency_tracker
        self.inference_fn = inference_fn
        self.max_workers = max_workers
        self.speed_factor = speed_factor
        self.failure_rate_threshold = failure_rate_threshold
        self.min_requests_for_circuit_break = min_requests_for_circuit_break
        self.user_metrics = defaultdict(list)
        self._metrics_lock = threading.Lock()
        self._active_count = 0
        self._active_lock = threading.Lock()
        self._max_observed_concurrency = 0
        self._total_completed = 0
        self._total_failed = 0
        self._circuit_broken = False

    def _execute_request(self, request, user_id):
        """执行单个推理请求"""
        with self._active_lock:
            self._active_count += 1
            self._max_observed_concurrency = max(
                self._max_observed_concurrency, self._active_count
            )

        try:
            if isinstance(request, dict):
                prompt = request["prompt"]
                max_tokens = request.get("max_tokens")
                ttft, tpot = self.inference_fn(prompt, max_tokens=max_tokens)
            else:
                ttft, tpot = self.inference_fn(request)

            is_failure = (ttft == float("inf") or tpot == float("inf"))

            self.latency_tracker.record(ttft, tpot)
            with self._metrics_lock:
                self.user_metrics[user_id].append((ttft, tpot))
                self._total_completed += 1
                if is_failure:
                    self._total_failed += 1
        finally:
            with self._active_lock:
                self._active_count -= 1

    def _check_circuit_break(self):
        """检查是否需要熔断（失败率过高则提前终止）"""
        with self._metrics_lock:
            if self._total_completed < self.min_requests_for_circuit_break:
                return False
            failure_rate = self._total_failed / self._total_completed
            if failure_rate >= self.failure_rate_threshold:
                self._circuit_broken = True
                return True
        return False

    def start(self, scheduled_requests, progress_interval=50):
        """
        按时间表发送所有请求。

        Args:
            scheduled_requests: 按时间排序的请求列表，每个元素为
                {"timestamp": float, "user_id": int, "request": str|dict}
            progress_interval: 每多少个请求打印一次进度
        """
        if not scheduled_requests:
            logger.warning("No requests to schedule")
            return

        total = len(scheduled_requests)
        base_time = scheduled_requests[0]["timestamp"]
        start_wall_time = time.time()
        submitted_count = 0

        logger.info(f"Realistic scheduler starting: {total} requests, "
                    f"speed_factor={self.speed_factor}x, "
                    f"max_workers={self.max_workers}")

        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = []

        # 重置熔断状态
        self._total_completed = 0
        self._total_failed = 0
        self._circuit_broken = False

        try:
            for i, item in enumerate(scheduled_requests):
                # 熔断检查：每 10 个请求检测一次
                if submitted_count > 0 and submitted_count % 10 == 0:
                    if self._check_circuit_break():
                        failure_rate = self._total_failed / max(self._total_completed, 1)
                        logger.warning(
                            f"  Circuit breaker triggered! "
                            f"failure_rate={failure_rate:.1%} >= {self.failure_rate_threshold:.0%}, "
                            f"completed={self._total_completed}, failed={self._total_failed}"
                        )
                        break

                # 计算这个请求应该在什么时候发送
                trace_elapsed = (item["timestamp"] - base_time) / self.speed_factor
                wall_elapsed = time.time() - start_wall_time

                # 如果还没到时间，等待
                wait_time = trace_elapsed - wall_elapsed
                if wait_time > 0:
                    time.sleep(wait_time)

                future = executor.submit(
                    self._execute_request,
                    item["request"],
                    item["user_id"]
                )
                futures.append(future)
                submitted_count += 1

                if submitted_count % progress_interval == 0:
                    logger.info(
                        f"  Progress: {submitted_count}/{total} submitted, "
                        f"active={self._active_count}, "
                        f"peak_concurrency={self._max_observed_concurrency}"
                    )

            # 等待所有已提交请求完成
            for future in futures:
                future.result()

        finally:
            executor.shutdown(wait=True)

        elapsed = time.time() - start_wall_time
        if self._circuit_broken:
            logger.info(
                f"Realistic scheduler ABORTED (circuit break): "
                f"{submitted_count} submitted in {elapsed:.1f}s, "
                f"peak_concurrency={self._max_observed_concurrency}"
            )
        else:
            logger.info(
                f"Realistic scheduler completed: {submitted_count} requests in {elapsed:.1f}s, "
                f"peak_concurrency={self._max_observed_concurrency}"
            )

    def get_user_metrics(self):
        """返回所有用户的指标数据"""
        with self._metrics_lock:
            all_metrics = []
            for user_id, metrics in self.user_metrics.items():
                for ttft, tpot in metrics:
                    all_metrics.append((user_id, ttft, tpot))
            return all_metrics

    def get_max_observed_concurrency(self):
        """返回测试期间观测到的最大并发数"""
        return self._max_observed_concurrency

    def is_circuit_broken(self):
        """返回当前轮次是否因熔断而提前终止"""
        return self._circuit_broken

    def get_failure_rate(self):
        """返回当前轮次的失败率"""
        with self._metrics_lock:
            if self._total_completed == 0:
                return 0.0
            return self._total_failed / self._total_completed
