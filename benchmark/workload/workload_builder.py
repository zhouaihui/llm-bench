# 负载模拟层：构建负载

# 负责：
# 生成用户
# 生成对话
# 生成请求时间

# 输出：User objects

# 例如：
# 100 users
# each 5 rounds

import random
from .user_model import User

class WorkloadBuilder:

    def __init__(self, prompt_generator):
        self.prompt_generator = prompt_generator

    def build_users(self, n):

        users = []

        for _ in range(n):

            prompts = [
                self.prompt_generator.sample()
                for _ in range(random.randint(3, 8))
            ]

            users.append(User(prompts))

        return users