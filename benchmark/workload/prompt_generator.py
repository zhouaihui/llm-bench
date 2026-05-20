# 负载模拟层：生成prompt
#
# 来源：
# prompt_templates.json

# 方法：随机采样

# 也可以扩展：
# 长度控制
# intent分类
# 复杂度控制

import random

class PromptGenerator:

    def __init__(self, templates):
        self.templates = templates

    def sample(self):
        return random.choice(self.templates)