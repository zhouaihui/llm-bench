# 负载模拟层：模拟真实用户

# 每个用户：
# 独立线程
# 独立对话状态

# 用户状态：
# conversation history
# current round
# prompt list

# 示例：user1

# round1 prompt
# round2 prompt
# round3 prompt

# 这样自然产生：KV cache 命中

class User:
    _id_counter = 0  # 类变量，用于生成唯一ID

    def __init__(self, prompts):
        self.prompts = prompts
        self.index = 0
        self.id = User._id_counter  # 分配唯一ID
        User._id_counter += 1

    def has_next(self):
        return self.index < len(self.prompts)

    def next_prompt(self):
        prompt = self.prompts[self.index]
        self.index += 1
        return prompt