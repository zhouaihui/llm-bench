# 整个benchmark的入口程序

# 负责：
# 初始化配置
# 初始化SLA引擎
# 初始化负载模拟
# 启动调度器
# 运行自动加压循环

# 整个benchmark的入口程序

# 负责：
# 初始化配置
# 初始化SLA引擎
# 初始化负载模拟
# 启动调度器
# 运行自动加压循环
# 输出完整 Benchmark 报告

import time
import random
import json
import numpy as np
from collections import defaultdict
import datetime

# 导入自定义模块
from controller.sla_engine import SLAEngine
from metrics.latency_tracker import LatencyTracker
from workload.prompt_generator import PromptGenerator
from workload.workload_builder import WorkloadBuilder
from scheduler.thread_manager import ThreadManager
from scheduler.conversation_scheduler import ConversationScheduler
from utils.logger import logger


# -----------------------------
# 模拟推理函数（随并发调整 TTFT/TPOT）
# -----------------------------
def fake_inference(prompt, concurrency_factor=1.0):
    base_ttft = random.uniform(0.15, 0.4)
    base_tpot = random.uniform(0.02, 0.04)
    ttft = base_ttft * (1 + 0.01 * concurrency_factor)
    tpot = base_tpot * (1 + 0.01 * concurrency_factor)
    time.sleep(random.uniform(0.01, 0.03))
    return ttft, tpot


# -----------------------------
# 用户级分析函数
# -----------------------------
def analyze_users(user_ttft_dict, user_tpot_dict, ttft_limit, tpot_limit):
    results = {}
    for user, ttfts in user_ttft_dict.items():
        tpots = user_tpot_dict[user]
        p99_ttft = np.percentile(ttfts, 99) if ttfts else 0
        p90_tpot = np.percentile(tpots, 90) if tpots else 0
        sla_status = "SAFE" if (p99_ttft < ttft_limit and p90_tpot < tpot_limit) else "VIOLATED"
        results[user] = {
            "p99_ttft": round(p99_ttft, 3),
            "p90_tpot": round(p90_tpot, 3),
            "sla_status": sla_status,
            "requests": len(ttfts)
        }
    return results


# -----------------------------
# 生成完整 Benchmark 报告
# -----------------------------
def generate_benchmark_report(user_ttft_dict, user_tpot_dict, max_safe_concurrency, total_rps,
                              test_start_time, test_end_time, ttft_limit, tpot_limit):
    all_ttft = [ttft for ttfts in user_ttft_dict.values() for ttft in ttfts]
    all_tpot = [tpot for tpots in user_tpot_dict.values() for tpot in tpots]

    avg_ttft = round(np.mean(all_ttft) * 1000, 1) if all_ttft else 0.0  # ms
    avg_tpot = round(np.mean(all_tpot) * 1000, 1) if all_tpot else 0.0  # ms
    total_requests = len(all_ttft)
    test_duration = round(test_end_time - test_start_time, 1)
    throughput_rps = round(total_requests / test_duration, 1) if test_duration > 0 else 0.0

    sla_info = {
        "P99_TTFT_limit_ms": int(ttft_limit * 1000),
        "P90_TPOT_limit_ms": int(tpot_limit * 1000)
    }

    result_info = {
        "max_concurrency": max_safe_concurrency,
        "average_ttft_ms": avg_ttft,
        "average_tpot_ms": avg_tpot,
        "throughput_rps": throughput_rps,
        "total_requests": total_requests,
        "test_duration_s": test_duration
    }

    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "SLA": sla_info,
        "Result": result_info
    }

    # 输出日志
    logger.info("\n====================================")
    logger.info("Benchmark Report")
    logger.info("====================================")
    logger.info(f"SLA: P99 TTFT < {sla_info['P99_TTFT_limit_ms']}ms, "
                f"P90 TPOT < {sla_info['P90_TPOT_limit_ms']}ms")
    logger.info(f"Result: Max Concurrency: {result_info['max_concurrency']}, "
                f"Average TTFT: {result_info['average_ttft_ms']}ms, "
                f"Average TPOT: {result_info['average_tpot_ms']}ms, "
                f"Throughput: {result_info['throughput_rps']} RPS, "
                f"Total Requests: {result_info['total_requests']}, "
                f"Test Duration: {result_info['test_duration_s']}s")

    with open("benchmark_result.json", "w") as f:
        json.dump(report, f, indent=4)
    logger.info("Benchmark report saved to benchmark_result.json")
    logger.info("====================================")


# -----------------------------
# Benchmark 主函数
# -----------------------------
def main():
    logger.info("====================================")
    logger.info("LLM SLA Benchmark Starting")
    logger.info("====================================")

    # SLA阈值
    TTFT_LIMIT = 0.5
    TPOT_LIMIT = 0.05

    sla_engine = SLAEngine(TTFT_LIMIT, TPOT_LIMIT)

    # 读取prompt模板
    with open("../data/prompt_templates.json") as f:
        templates = json.load(f)

    prompt_generator = PromptGenerator(templates)
    workload_builder = WorkloadBuilder(prompt_generator)

    # Binary Search 自动寻找最大容量
    low = 1
    high = 200  # 最大并发上限
    max_safe_concurrency = 0
    rps_total = 100  # 总目标RPS
    max_user_results = {}  # 保存最终最大并发用户指标
    estimated_rps = 0

    test_start_time = time.time()

    while low <= high:
        concurrency = (low + high) // 2
        logger.info(f"\nTesting concurrency: {concurrency}")

        # 多轮测试取平均，增加稳定性
        num_trials = 3
        trial_states = []
        trial_durations = []
        trial_latencies = []

        for trial in range(num_trials):
            latency_tracker = LatencyTracker(window_seconds=60)
            users = workload_builder.build_users(concurrency)
            thread_manager = ThreadManager(max_workers=concurrency)
            scheduler = ConversationScheduler(
                thread_manager,
                latency_tracker,
                lambda prompt: fake_inference(prompt, concurrency)
            )

            rps_per_user = rps_total / concurrency

            start_trial_time = time.time()
            scheduler.start(users, rps=rps_per_user)
            end_trial_time = time.time()
            duration = end_trial_time - start_trial_time

            # 使用 Sliding Window 最近 60 秒数据
            p99_ttft = latency_tracker.p99_ttft()
            p90_tpot = latency_tracker.p90_tpot()
            state = sla_engine.check(latency_tracker.get_ttft_window(),
                                     latency_tracker.get_tpot_window())

            trial_states.append(state)
            trial_durations.append(duration)
            trial_latencies.append((p99_ttft, p90_tpot))

        # 判断平均状态
        if trial_states.count("SAFE") >= 2:  # 至少2/3轮 SAFE
            max_safe_concurrency = concurrency
            low = concurrency + 1

            # 保存最大并发下的用户指标
            user_ttft_dict = defaultdict(list)
            user_tpot_dict = defaultdict(list)
            for user, ttft, tpot in scheduler.get_user_metrics():
                user_ttft_dict[user].append(ttft)
                user_tpot_dict[user].append(tpot)
            max_user_results = analyze_users(user_ttft_dict, user_tpot_dict, TTFT_LIMIT, TPOT_LIMIT)

            # 估算吞吐量
            estimated_rps = sum(len(ttfts) for ttfts in user_ttft_dict.values()) / np.mean(trial_durations)
        else:
            high = concurrency - 1

    test_end_time = time.time()

    # -----------------------------
    # 输出用户分析结果
    # -----------------------------
    logger.info("\n====================================")
    logger.info("User-level Analysis & Benchmark Summary")
    logger.info("====================================")
    for user, metrics in max_user_results.items():
        logger.info(f"User: {user}, Requests: {metrics['requests']}, "
                    f"P99 TTFT: {metrics['p99_ttft']}s, P90 TPOT: {metrics['p90_tpot']}s, SLA: {metrics['sla_status']}")

    logger.info(f"\nMax Stable Concurrency: {max_safe_concurrency}")
    logger.info(f"Estimated Throughput: ~{estimated_rps:.2f} RPS")

    # 保存用户分析结果
    with open("user_analysis.json", "w") as f:
        json.dump(max_user_results, f, indent=4)
    logger.info("User analysis saved to user_analysis.json")

    # -----------------------------
    # 输出完整 Benchmark 报告
    # -----------------------------
    generate_benchmark_report(
        user_ttft_dict=user_ttft_dict,
        user_tpot_dict=user_tpot_dict,
        max_safe_concurrency=max_safe_concurrency,
        total_rps=rps_total,
        test_start_time=test_start_time,
        test_end_time=test_end_time,
        ttft_limit=TTFT_LIMIT,
        tpot_limit=TPOT_LIMIT
    )


if __name__ == "__main__":
    main()