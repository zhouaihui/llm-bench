# 调度层：对话调度器
#
# 负责调度多个用户并行执行对话任务
# 使用线程锁保证 user_metrics 的线程安全

from collections import defaultdict
import threading
import random
import time
import math


class ConversationScheduler:
    """
    会话调度器，负责调度多个用户并行执行对话任务
    """

    def __init__(self, thread_manager, latency_tracker, inference_fn):
        self.thread_manager = thread_manager
        self.latency_tracker = latency_tracker
        self.inference_fn = inference_fn
        self.user_metrics = defaultdict(list)
        self._metrics_lock = threading.Lock()

    def run_user(self, user, rps):
        while user.has_next():
            request = user.next_prompt()

            # 支持两种格式：字符串（传统）或字典（trace 模式）
            if isinstance(request, dict):
                prompt = request["prompt"]
                max_tokens = request.get("max_tokens")
                ttft, tpot = self.inference_fn(prompt, max_tokens=max_tokens)
            else:
                ttft, tpot = self.inference_fn(request)

            if math.isfinite(ttft) and math.isfinite(tpot):
                self.latency_tracker.record(ttft, tpot)
                with self._metrics_lock:
                    self.user_metrics[user.id].append((ttft, tpot))

            sleep_time = random.expovariate(rps)
            time.sleep(sleep_time)

    def start(self, users, rps=1.0):
        for user in users:
            self.thread_manager.submit(self.run_user, user, rps)
        self.thread_manager.wait()

    def get_user_metrics(self):
        with self._metrics_lock:
            all_metrics = []
            for user_id, metrics in self.user_metrics.items():
                for ttft, tpot in metrics:
                    all_metrics.append((user_id, ttft, tpot))
            return all_metrics
