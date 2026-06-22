import random
from .user_model import User


class WorkloadBuilder:

    def __init__(self, prompt_generator, conversation_rounds=None):
        self.prompt_generator = prompt_generator
        self.min_rounds = 3
        self.max_rounds = 10
        if conversation_rounds and len(conversation_rounds) == 2:
            self.min_rounds = conversation_rounds[0]
            self.max_rounds = conversation_rounds[1]

    def build_users(self, n):
        """原有方法：基于模板随机生成用户请求"""
        User.reset_id_counter()
        users = []
        for _ in range(n):
            num_rounds = random.randint(self.min_rounds, self.max_rounds)
            prompts = [
                self.prompt_generator.sample()
                for _ in range(num_rounds)
            ]
            users.append(User(prompts))
        return users

    def build_users_from_trace(self, trace_loader, num_users,
                               max_input_tokens=None):
        """
        基于 Kimi trace 数据构建用户请求。

        每个用户对应一个 trace session（多轮对话），
        prompt 基于模板扩展到 trace 中记录的 input_length，
        max_tokens 使用 trace 中的 output_length。

        Args:
            trace_loader: TraceLoader 实例
            num_users: 需要构建的用户数
            max_input_tokens: 限制最大输入 token 数（避免超模型上下文）
        """
        User.reset_id_counter()

        sessions = trace_loader.sample_sessions(num_users)
        users = []

        for session in sessions:
            requests = []
            for record in session:
                input_length = record.input_length
                if max_input_tokens:
                    input_length = min(input_length, max_input_tokens)

                prompt = self._build_prompt_by_length(input_length)
                requests.append({
                    "prompt": prompt,
                    "max_tokens": record.output_length,
                    "input_length": input_length,
                })

            users.append(User(requests))

        return users

    def build_scheduled_requests(self, trace_loader, max_requests=None,
                                 max_input_tokens=None):
        """
        基于 trace 的 timestamp 构建全局时间表，供 RealisticScheduler 使用。

        按 trace 中的 timestamp 排序所有请求，每个请求携带发送时间、
        用户 ID 和构建好的 prompt。用户 ID 基于会话分组自动分配。

        Args:
            trace_loader: TraceLoader 实例
            max_requests: 最大请求数（None 表示使用全部 trace 记录）
            max_input_tokens: 限制最大输入 token 数

        Returns:
            按 timestamp 排序的请求列表，每个元素为：
            {"timestamp": float, "user_id": int, "request": dict}
        """
        ordered_records = trace_loader.get_time_ordered_records()

        if max_requests and len(ordered_records) > max_requests:
            ordered_records = ordered_records[:max_requests]

        # 为每条记录分配 user_id（基于会话分组）
        record_to_user = self._assign_user_ids(ordered_records)

        scheduled = []
        for record in ordered_records:
            input_length = record.input_length
            if max_input_tokens:
                input_length = min(input_length, max_input_tokens)

            prompt = self._build_prompt_by_length(input_length)
            scheduled.append({
                "timestamp": float(record.timestamp),
                "user_id": record_to_user[id(record)],
                "request": {
                    "prompt": prompt,
                    "max_tokens": record.output_length,
                    "input_length": input_length,
                },
            })

        return scheduled

    def _assign_user_ids(self, records):
        """
        根据 hash_ids 前缀关系为记录分配 user_id。

        共享较长 hash_ids 前缀的请求被视为同一用户的多轮会话。
        使用贪心策略：将每条记录与已有用户的最后一条请求比较前缀重叠度，
        如果超过阈值则归入该用户，否则分配新用户。
        """
        record_to_user = {}
        user_last_record = {}
        next_user_id = 0

        for record in records:
            best_user = None
            best_overlap = 0.0

            for user_id, last_record in user_last_record.items():
                overlap = self._prefix_overlap_ratio(
                    last_record.hash_ids, record.hash_ids
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_user = user_id

            if best_user is not None and best_overlap >= 0.5:
                assigned_user = best_user
            else:
                assigned_user = next_user_id
                next_user_id += 1

            record_to_user[id(record)] = assigned_user
            user_last_record[assigned_user] = record

        return record_to_user

    @staticmethod
    def _prefix_overlap_ratio(ids_a, ids_b):
        """计算两个 hash_ids 列表的前缀重叠比例"""
        if not ids_a or not ids_b:
            return 0.0
        min_length = min(len(ids_a), len(ids_b))
        overlap_count = 0
        for i in range(min_length):
            if ids_a[i] == ids_b[i]:
                overlap_count += 1
            else:
                break
        return overlap_count / min_length

    def _build_prompt_by_length(self, target_token_count):
        """
        根据目标 token 数构建 prompt。

        粗略估算：1 个英文单词 ≈ 1.3 token，1 个字符 ≈ 0.25 token。
        用模板拼接重复来填充到目标长度。
        """
        base_prompt = self.prompt_generator.sample()
        estimated_tokens = len(base_prompt.split()) * 1.3

        if estimated_tokens >= target_token_count:
            return base_prompt

        filler_parts = [base_prompt]
        current_tokens = estimated_tokens

        while current_tokens < target_token_count:
            extra = self.prompt_generator.sample()
            extra_tokens = len(extra.split()) * 1.3
            filler_parts.append(extra)
            current_tokens += extra_tokens

        return "\n\n".join(filler_parts)
