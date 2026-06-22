from concurrent.futures import ThreadPoolExecutor


class ThreadManager:

    def __init__(self, max_workers):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures = []

    def submit(self, func, *args):
        future = self.executor.submit(func, *args)
        self.futures.append(future)

    def wait(self):
        for future in self.futures:
            future.result()
        self.futures = []

    def shutdown(self):
        self.executor.shutdown(wait=True)
        self.futures = []