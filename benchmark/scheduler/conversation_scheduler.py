# 调度层：对话调度器

# 负责：
# 创建用户线程
# 控制对话轮数
# 发送请求

# 每个用户：一个线程

# 使用：
# ThreadPoolExecutor

# 结构：
# ThreadPool
#    ├ user1
#    ├ user2
#    ├ user3

from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import random
import time

class ConversationScheduler:
    """
    会话调度器，负责调度多个用户并行执行对话任务
    """

    def __init__(self, thread_manager, latency_tracker, inference_fn):
        self.thread_manager = thread_manager
        self.latency_tracker = latency_tracker
        self.inference_fn = inference_fn
        # 新增：用户级指标存储
        self.user_metrics = defaultdict(list)  # {user_id: [(ttft, tpot), ...]}

    def run_user(self, user, rps):
        while user.has_next():
            prompt = user.next_prompt()
            ttft, tpot = self.inference_fn(prompt)
            self.latency_tracker.record(ttft, tpot)
            self.user_metrics[user.id].append((ttft, tpot))  # ← 这里必须加

            # Poisson arrival
            sleep_time = random.expovariate(rps)
            time.sleep(sleep_time)

    def start(self, users, rps=1.0):
        for user in users:
            self.thread_manager.submit(self.run_user, user, rps)
        self.thread_manager.wait()

    # -----------------------------
    # 新增方法：获取用户级指标
    # -----------------------------
    def get_user_metrics(self):
        """
        返回格式：
        [(user_id, ttft, tpot), ...]
        """
        all_metrics = []
        for user_id, metrics in self.user_metrics.items():
            for ttft, tpot in metrics:
                all_metrics.append((user_id, ttft, tpot))
        return all_metrics