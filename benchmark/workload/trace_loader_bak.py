"""
Trace 数据加载器

从 Kimi Mooncake (FAST'25) 开源 trace 数据中加载真实的 LLM 推理请求分布。
每条 trace 包含：
  - timestamp: 请求到达时间（秒）
  - input_length: 输入 token 数
  - output_length: 输出 token 数
  - hash_ids: KV cache block IDs（标识 prefix 复用关系）

支持两种使用模式：
  1. 会话模式：按 hash_ids 前缀分组为多轮对话
  2. 真实负载模式：按 timestamp 还原真实的请求到达时间，模拟突发流量
"""

import json
import random
from collections import defaultdict
from typing import List, Tuple, Optional

import numpy as np


class TraceRecord:
    """单条 trace 记录"""

    def __init__(self, timestamp: int, input_length: int,
                 output_length: int, hash_ids: List[int]):
        self.timestamp = timestamp
        self.input_length = input_length
        self.output_length = output_length
        self.hash_ids = hash_ids


class TraceLoader:
    """从 JSONL 文件加载 trace 数据并构建会话"""

    def __init__(self, trace_path: str, max_records: Optional[int] = None):
        self.trace_path = trace_path
        self.records: List[TraceRecord] = []
        self._load(max_records)

    def _load(self, max_records: Optional[int]):
        with open(self.trace_path) as f:
            for i, line in enumerate(f):
                if max_records and i >= max_records:
                    break
                data = json.loads(line)
                self.records.append(TraceRecord(
                    timestamp=data["timestamp"],
                    input_length=data["input_length"],
                    output_length=data["output_length"],
                    hash_ids=data.get("hash_ids", [])
                ))

    def get_sessions(self) -> List[List[TraceRecord]]:
        """
        根据 hash_ids 前缀重叠度将请求分组为会话。

        先按 hash_ids[0] 粗分组，再根据相邻请求的 hash_ids 前缀
        重叠比例进一步细分为子会话，使分组更接近真实的多轮对话。
        """
        coarse_groups = defaultdict(list)
        for record in self.records:
            if record.hash_ids:
                session_key = record.hash_ids[0]
            else:
                session_key = id(record)
            coarse_groups[session_key].append(record)

        sessions = []
        for records in coarse_groups.values():
            sorted_records = sorted(records, key=lambda r: r.timestamp)
            sub_sessions = self._split_by_prefix_overlap(sorted_records)
            sessions.extend(sub_sessions)

        return sessions

    def _split_by_prefix_overlap(self, records: List[TraceRecord]) -> List[List[TraceRecord]]:
        """
        将共享 hash_ids[0] 的记录按前缀重叠度细分为子会话。

        相邻请求如果 hash_ids 前缀重叠超过 50%，则归入同一子会话。
        """
        if len(records) <= 1:
            return [records]

        sub_sessions = []
        current_session = [records[0]]

        for i in range(1, len(records)):
            previous = records[i - 1]
            current = records[i]
            overlap = self._prefix_overlap_ratio(previous.hash_ids, current.hash_ids)
            if overlap >= 0.5:
                current_session.append(current)
            else:
                sub_sessions.append(current_session)
                current_session = [current]

        sub_sessions.append(current_session)
        return sub_sessions

    @staticmethod
    def _prefix_overlap_ratio(ids_a: List[int], ids_b: List[int]) -> float:
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

    def get_time_ordered_records(self) -> List[TraceRecord]:
        """返回按 timestamp 排序的所有记录"""
        return sorted(self.records, key=lambda r: r.timestamp)

    def get_arrival_intervals(self) -> List[float]:
        """
        计算请求到达间隔（秒），反映真实的流量模式。

        Returns:
            相邻请求之间的时间间隔列表
        """
        ordered = self.get_time_ordered_records()
        if len(ordered) < 2:
            return []
        intervals = []
        for i in range(1, len(ordered)):
            interval = ordered[i].timestamp - ordered[i - 1].timestamp
            intervals.append(max(0.0, float(interval)))
        return intervals

    def slice_time_window(self, duration_seconds: int,
                          target_concurrency: int) -> List[TraceRecord]:
        """
        从 trace 中截取一个时间窗口的请求，并按目标并发数缩放。

        Args:
            duration_seconds: 时间窗口长度（秒）
            target_concurrency: 目标并发用户数

        Returns:
            缩放后的请求列表，保留相对时间关系
        """
        ordered = self.get_time_ordered_records()
        if not ordered:
            return []

        base_timestamp = ordered[0].timestamp
        window_records = [
            r for r in ordered
            if (r.timestamp - base_timestamp) <= duration_seconds
        ]

        if not window_records:
            return ordered[:target_concurrency]

        time_span = window_records[-1].timestamp - window_records[0].timestamp
        original_rps = len(window_records) / max(time_span, 1)

        scale_factor = target_concurrency / max(original_rps, 0.1)
        target_count = max(1, int(len(window_records) * scale_factor))
        target_count = min(target_count, len(window_records))

        if target_count >= len(window_records):
            sampled = window_records
        else:
            indices = np.linspace(0, len(window_records) - 1, target_count, dtype=int)
            sampled = [window_records[i] for i in indices]

        return sampled

    def get_burst_windows(self, threshold_multiplier: float = 2.0) -> List[Tuple[int, int, int]]:
        """
        检测流量突发（burst）窗口。

        Args:
            threshold_multiplier: 超过平均 RPS 多少倍算突发

        Returns:
            [(window_start, window_end, request_count), ...] 突发窗口列表
        """
        ordered = self.get_time_ordered_records()
        if len(ordered) < 2:
            return []

        total_span = ordered[-1].timestamp - ordered[0].timestamp
        average_rps = len(ordered) / max(total_span, 1)
        threshold = average_rps * threshold_multiplier

        bursts = []
        base = ordered[0].timestamp
        timestamps = [r.timestamp for r in ordered]
        max_ts = max(timestamps)

        for start in range(int(base), int(max_ts)):
            end = start + 1
            count = sum(1 for ts in timestamps if start <= ts < end)
            if count > threshold:
                bursts.append((start, end, count))

        return bursts

    def sample_requests(self, count: int) -> List[TraceRecord]:
        """随机采样指定数量的请求"""
        if count >= len(self.records):
            return list(self.records)
        return random.sample(self.records, count)

    def sample_sessions(self, count: int) -> List[List[TraceRecord]]:
        """随机采样指定数量的会话"""
        sessions = self.get_sessions()
        if count >= len(sessions):
            return sessions
        return random.sample(sessions, count)

    def get_input_length_distribution(self) -> List[int]:
        """获取输入长度分布"""
        return [r.input_length for r in self.records]

    def get_output_length_distribution(self) -> List[int]:
        """获取输出长度分布"""
        return [r.output_length for r in self.records]

    def summary(self) -> dict:
        """返回 trace 数据的统计摘要"""
        inputs = self.get_input_length_distribution()
        outputs = self.get_output_length_distribution()
        sessions = self.get_sessions()
        session_lengths = [len(s) for s in sessions]
        intervals = self.get_arrival_intervals()
        bursts = self.get_burst_windows()

        result = {
            "total_records": len(self.records),
            "total_sessions": len(sessions),
            "input_length": {
                "min": min(inputs), "max": max(inputs),
                "median": int(np.median(inputs)),
                "mean": int(np.mean(inputs)),
                "p90": int(np.percentile(inputs, 90)),
            },
            "output_length": {
                "min": min(outputs), "max": max(outputs),
                "median": int(np.median(outputs)),
                "mean": int(np.mean(outputs)),
                "p90": int(np.percentile(outputs, 90)),
            },
            "session_length": {
                "min": min(session_lengths), "max": max(session_lengths),
                "median": int(np.median(session_lengths)),
                "mean": round(float(np.mean(session_lengths)), 1),
            },
        }

        if intervals:
            result["arrival_intervals"] = {
                "min": round(min(intervals), 3),
                "max": round(max(intervals), 3),
                "median": round(float(np.median(intervals)), 3),
                "mean": round(float(np.mean(intervals)), 3),
                "p90": round(float(np.percentile(intervals, 90)), 3),
            }

        if bursts:
            result["burst_windows"] = len(bursts)

        return result
