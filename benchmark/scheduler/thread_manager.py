# 调度层：线程池管理

# 负责：
# 线程创建
# 线程回收
# 最大线程控制

# 本质上是：
# ThreadPoolExecutor 的封装

# 例如：
# max_workers = 100

from concurrent.futures import ThreadPoolExecutor

from concurrent.futures import ThreadPoolExecutor

class ThreadManager:
    # 线程管理器，用于提交任务并管理线程池

    def __init__(self, max_workers):
        # 初始化线程池
        # max_workers: 最大线程数
        self.executor = ThreadPoolExecutor(max_workers=max_workers)  # 创建线程池
        self.futures = []  # 用于保存提交任务的Future对象

    def submit(self, func, *args):
        # 提交任务到线程池
        # func: 要执行的函数
        # args: 函数参数
        future = self.executor.submit(func, *args)  # 提交任务
        self.futures.append(future)  # 保存Future对象，方便等待结果

    def wait(self):
        # 等待所有提交的线程执行完成
        for future in self.futures:
            future.result()  # 阻塞等待线程完成并获取结果
        self.futures = []  # 清空列表，准备下一轮任务