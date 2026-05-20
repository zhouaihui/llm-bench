# 整个benchmark的入口程序
#
# 负责：
# 1. 从配置文件加载 SLA 阈值和负载参数
# 2. 初始化 SLA 引擎、负载模拟、调度器
# 3. 通过 Binary Search 自动寻找最大安全并发数
# 4. 输出完整 Benchmark 报告

import os
import time
import random
import json
import numpy as np
from collections import defaultdict
import datetime

from controller.sla_engine import SLAEngine
from metrics.latency_tracker import LatencyTracker
from workload.prompt_generator import PromptGenerator
from workload.workload_builder import WorkloadBuilder
from workload.trace_loader import TraceLoader
from scheduler.thread_manager import ThreadManager
from scheduler.conversation_scheduler import ConversationScheduler
from utils.config_loader import load_yaml
from utils.logger import logger
from inference.real_inference import create_inference

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def fake_inference(prompt, concurrency_factor=1.0, max_tokens=None):
    base_ttft = random.uniform(0.15, 0.4)
    base_tpot = random.uniform(0.02, 0.04)
    ttft = base_ttft * (1 + 0.05 * concurrency_factor)
    tpot = base_tpot * (1 + 0.05 * concurrency_factor)
    time.sleep(ttft * 0.1)
    return ttft, tpot



def analyze_users(user_ttft_dict, user_tpot_dict, ttft_limit, tpot_limit):
    results = {}
    for user, ttfts in user_ttft_dict.items():
        tpots = user_tpot_dict.get(user, [])
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



def generate_benchmark_report(user_ttft_dict, user_tpot_dict, max_safe_concurrency, total_rps,
                              test_start_time, test_end_time, ttft_limit, tpot_limit,
                              model_name="unknown", inference_type="fake",
                              trace_info=None, user_results=None):
    all_ttft = [ttft for ttfts in user_ttft_dict.values() for ttft in ttfts]
    all_tpot = [tpot for tpots in user_tpot_dict.values() for tpot in tpots]

    avg_ttft = round(np.mean(all_ttft) * 1000, 1) if all_ttft else 0.0
    avg_tpot = round(np.mean(all_tpot) * 1000, 1) if all_tpot else 0.0
    p99_ttft = round(np.percentile(all_ttft, 99) * 1000, 1) if all_ttft else 0.0
    p90_tpot = round(np.percentile(all_tpot, 90) * 1000, 1) if all_tpot else 0.0
    total_requests = len(all_ttft)
    test_duration = round(test_end_time - test_start_time, 1)
    throughput_rps = round(total_requests / test_duration, 1) if test_duration > 0 else 0.0

    ttft_limit_ms = int(ttft_limit * 1000)
    tpot_limit_ms = int(tpot_limit * 1000)

    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")

    # 生成安全的文件名（替换特殊字符）
    safe_model_name = model_name.replace("/", "_").replace("\\", "_").replace(" ", "_").strip("_")
    # 截取模型名最后一段作为短名
    short_model_name = safe_model_name.split("_")[-1] if "_" in safe_model_name else safe_model_name

    # 报告目录
    reports_dir = os.path.join(BASE_DIR, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    report_filename = f"{timestamp_str}_{short_model_name}.md"
    report_path = os.path.join(reports_dir, report_filename)

    # 构建 Markdown 报告
    sla_ttft_status = "✅ PASS" if p99_ttft <= ttft_limit_ms else "❌ FAIL"
    sla_tpot_status = "✅ PASS" if p90_tpot <= tpot_limit_ms else "❌ FAIL"

    lines = [
        f"## LLM SLA Benchmark Report",
        f"",
        f"**Generated**: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"### Model & Configuration",
        f"",
        f"| Item | Value |",
        f"|------|-------|",
        f"| **Model** | `{model_name}` |",
        f"| **Inference Type** | {inference_type} |",
    ]

    if trace_info:
        lines.append(f"| **Trace Data** | `{trace_info.get('trace_file', 'N/A')}` |")
        lines.append(f"| **Trace Records** | {trace_info.get('total_records', 'N/A')} |")
        lines.append(f"| **Trace Sessions** | {trace_info.get('total_sessions', 'N/A')} |")
    else:
        lines.append(f"| **Workload Mode** | Template (fixed prompts) |")

    lines += [
        f"",
        f"### SLA Thresholds",
        f"",
        f"| Metric | Threshold | Measured | Status |",
        f"|--------|-----------|----------|--------|",
        f"| P99 TTFT | < {ttft_limit_ms}ms | {p99_ttft}ms | {sla_ttft_status} |",
        f"| P90 TPOT | < {tpot_limit_ms}ms | {p90_tpot}ms | {sla_tpot_status} |",
        f"",
        f"### Core Results",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| **Max Stable Concurrency** | **{max_safe_concurrency}** |",
        f"| Average TTFT | {avg_ttft}ms |",
        f"| P99 TTFT | {p99_ttft}ms |",
        f"| Average TPOT | {avg_tpot}ms |",
        f"| P90 TPOT | {p90_tpot}ms |",
        f"| Throughput | {throughput_rps} RPS |",
        f"| Total Requests | {total_requests} |",
        f"| Test Duration | {test_duration}s |",
        f"",
    ]

    # 用户级别详情
    if user_results:
        lines += [
            f"### User-level Details",
            f"",
            f"| User | Requests | P99 TTFT | P90 TPOT | SLA |",
            f"|------|----------|----------|----------|-----|",
        ]
        for user_id, metrics in sorted(user_results.items()):
            lines.append(
                f"| {user_id} | {metrics['requests']} | "
                f"{metrics['p99_ttft']}s | {metrics['p90_tpot']}s | "
                f"{metrics['sla_status']} |"
            )
        lines.append("")

    markdown_content = "\n".join(lines)

    with open(report_path, "w") as f:
        f.write(markdown_content)

    # 同时保存 JSON 格式（兼容旧逻辑）
    json_report = {
        "timestamp": now.isoformat(),
        "model": model_name,
        "inference_type": inference_type,
        "SLA": {"P99_TTFT_limit_ms": ttft_limit_ms, "P90_TPOT_limit_ms": tpot_limit_ms},
        "Result": {
            "max_concurrency": max_safe_concurrency,
            "average_ttft_ms": avg_ttft, "p99_ttft_ms": p99_ttft,
            "average_tpot_ms": avg_tpot, "p90_tpot_ms": p90_tpot,
            "throughput_rps": throughput_rps,
            "total_requests": total_requests,
            "test_duration_s": test_duration
        }
    }
    json_path = os.path.join(reports_dir, f"{timestamp_str}_{short_model_name}.json")
    with open(json_path, "w") as f:
        json.dump(json_report, f, indent=4)

    # 日志输出
    logger.info("\n====================================")
    logger.info("Benchmark Report")
    logger.info("====================================")
    logger.info(f"Model: {model_name}")
    logger.info(f"SLA: P99 TTFT < {ttft_limit_ms}ms ({sla_ttft_status}), "
                f"P90 TPOT < {tpot_limit_ms}ms ({sla_tpot_status})")
    logger.info(f"Result: Max Concurrency: {max_safe_concurrency}, "
                f"Average TTFT: {avg_ttft}ms, Average TPOT: {avg_tpot}ms, "
                f"Throughput: {throughput_rps} RPS, "
                f"Total Requests: {total_requests}, "
                f"Test Duration: {test_duration}s")
    logger.info(f"Report saved to {report_path}")
    logger.info(f"JSON saved to {json_path}")
    logger.info("====================================")



def main():
    logger.info("====================================")
    logger.info("LLM SLA Benchmark Starting")
    logger.info("====================================")

    sla_config = load_yaml(os.path.join(BASE_DIR, "config", "sla.yaml"))
    workload_config = load_yaml(os.path.join(BASE_DIR, "config", "workload.yaml"))

    TTFT_LIMIT = float(sla_config.get("ttft_p99", 0.5))
    TPOT_LIMIT = float(sla_config.get("tpot_p90", 0.05))
    window_size = int(sla_config.get("window_size", 60))
    observe_windows = int(sla_config.get("observe_windows", 3))
    max_users = int(workload_config.get("max_users", 200))
    conversation_rounds = workload_config.get("conversation_rounds", [3, 10])

    # 推理配置
    inference_type = workload_config.get("inference_type", "fake")
    inference_config = workload_config.get("inference", {})

    # 调度模式：classic（原有二分搜索）或 realistic（trace 时间驱动）
    schedule_mode = workload_config.get("schedule_mode", "classic")

    sla_engine = SLAEngine(TTFT_LIMIT, TPOT_LIMIT)

    prompt_path = os.path.join(BASE_DIR, "data", "prompt_templates.json")
    with open(prompt_path) as f:
        templates = json.load(f)

    prompt_generator = PromptGenerator(templates)
    workload_builder = WorkloadBuilder(prompt_generator, conversation_rounds=conversation_rounds)

    # Trace 数据配置
    trace_config = workload_config.get("trace_data", {})
    trace_loader = None
    use_trace = trace_config.get("enabled", False)

    if use_trace:
        trace_file = trace_config.get("trace_file", "")
        trace_path = os.path.join(BASE_DIR, trace_file) if trace_file else ""
        max_records = trace_config.get("max_records")

        if trace_path and os.path.exists(trace_path):
            trace_loader = TraceLoader(trace_path, max_records=max_records)
            summary = trace_loader.summary()
            logger.info(f"Loaded trace data: {trace_file}")
            logger.info(f"  Records: {summary['total_records']}, Sessions: {summary['total_sessions']}")
            logger.info(f"  Input length: median={summary['input_length']['median']}, "
                        f"p90={summary['input_length']['p90']}")
            logger.info(f"  Output length: median={summary['output_length']['median']}, "
                        f"p90={summary['output_length']['p90']}")
            logger.info(f"  Session rounds: mean={summary['session_length']['mean']}")
            if "arrival_intervals" in summary:
                logger.info(f"  Arrival intervals: median={summary['arrival_intervals']['median']}s, "
                            f"p90={summary['arrival_intervals']['p90']}s")
            if "burst_windows" in summary:
                logger.info(f"  Burst windows detected: {summary['burst_windows']}")
        else:
            logger.warning(f"Trace file not found: {trace_path}, falling back to template mode")
            use_trace = False

    # 创建推理接口
    if inference_type == "fake":
        inference_fn = fake_inference
        logger.info("Using fake inference (simulation mode)")
    else:
        inference_obj = create_inference(inference_type, **inference_config)
        logger.info(f"Using {inference_type} inference: {inference_config}")

        def inference_fn(prompt, concurrency_factor=1.0, max_tokens=None):
            return inference_obj.infer(prompt, max_tokens=max_tokens)

    # ============================================================
    # 真实负载模式（realistic）：自动加压找极限
    # 每轮固定时间窗口，二分搜索请求密度，直到 SLA 被突破
    # ============================================================
    if schedule_mode == "realistic" and use_trace and trace_loader:
        logger.info("\n====================================")
        logger.info("Mode: REALISTIC (auto stress test)")
        logger.info("====================================")

        from scheduler.realistic_scheduler import RealisticScheduler
        import copy

        speed_factor = float(workload_config.get("speed_factor", 1.0))
        max_input_tokens = trace_config.get("max_input_tokens")
        target_duration = float(workload_config.get("replay_duration_seconds", 300))

        # 加压参数
        pressure_config = workload_config.get("pressure", {})
        min_rps = float(pressure_config.get("min_rps", 0.5))
        max_rps = float(pressure_config.get("max_rps", 20.0))
        rps_precision = float(pressure_config.get("rps_precision", 0.5))
        safe_confirm_rounds = int(pressure_config.get("safe_confirm_rounds", 1))

        # 预构建所有请求（只做一次，后续按 RPS 采样）
        logger.info("Building request pool from trace data...")
        all_scheduled = workload_builder.build_scheduled_requests(
            trace_loader, max_requests=None, max_input_tokens=max_input_tokens)
        logger.info(f"Request pool ready: {len(all_scheduled)} requests")

        # ---- 数据集深度分析 ----
        logger.info("\n-------- Trace Dataset Analysis --------")
        input_lengths = [r["request"]["input_length"] for r in all_scheduled]
        output_lengths = [r["request"]["max_tokens"] for r in all_scheduled]
        unique_user_ids = set(r["user_id"] for r in all_scheduled)

        # 输入长度分段
        short_input = sum(1 for x in input_lengths if x <= 1024)
        medium_input = sum(1 for x in input_lengths if 1024 < x <= 4096)
        long_input = sum(1 for x in input_lengths if x > 4096)
        total = len(input_lengths)
        logger.info(f"Input length distribution ({total} requests):")
        logger.info(f"  Short  (<=1K tokens): {short_input} ({100*short_input/total:.1f}%)")
        logger.info(f"  Medium (1K~4K tokens): {medium_input} ({100*medium_input/total:.1f}%)")
        logger.info(f"  Long   (>4K tokens):  {long_input} ({100*long_input/total:.1f}%)")
        logger.info(f"  Percentiles: p50={int(np.median(input_lengths))}, "
                    f"p90={int(np.percentile(input_lengths, 90))}, "
                    f"p99={int(np.percentile(input_lengths, 99))}")

        # 输出长度分段
        short_output = sum(1 for x in output_lengths if x <= 100)
        medium_output = sum(1 for x in output_lengths if 100 < x <= 500)
        long_output = sum(1 for x in output_lengths if x > 500)
        logger.info(f"Output length distribution:")
        logger.info(f"  Short  (<=100 tokens): {short_output} ({100*short_output/total:.1f}%)")
        logger.info(f"  Medium (100~500 tokens): {medium_output} ({100*medium_output/total:.1f}%)")
        logger.info(f"  Long   (>500 tokens):  {long_output} ({100*long_output/total:.1f}%)")
        logger.info(f"  Percentiles: p50={int(np.median(output_lengths))}, "
                    f"p90={int(np.percentile(output_lengths, 90))}, "
                    f"p99={int(np.percentile(output_lengths, 99))}")

        # 用户行为分析
        user_request_counts = defaultdict(int)
        for r in all_scheduled:
            user_request_counts[r["user_id"]] += 1
        counts = list(user_request_counts.values())
        logger.info(f"User behavior ({len(unique_user_ids)} unique users):")
        logger.info(f"  Requests per user: mean={np.mean(counts):.1f}, "
                    f"median={int(np.median(counts))}, max={max(counts)}")
        single_turn = sum(1 for c in counts if c == 1)
        multi_turn = sum(1 for c in counts if c > 1)
        logger.info(f"  Single-turn users: {single_turn} ({100*single_turn/len(counts):.1f}%)")
        logger.info(f"  Multi-turn users:  {multi_turn} ({100*multi_turn/len(counts):.1f}%)")

        # 根据数据特征估算合理 RPS 范围
        avg_input = np.mean(input_lengths)
        avg_output = np.mean(output_lengths)
        # 粗估每请求耗时: TTFT + output_tokens * TPOT
        estimated_request_time = TTFT_LIMIT * 0.3 + avg_output * TPOT_LIMIT * 0.5
        estimated_max_rps = max_users / max(estimated_request_time, 0.1)
        logger.info(f"Estimated request latency: ~{estimated_request_time:.1f}s "
                    f"(avg_input={int(avg_input)}, avg_output={int(avg_output)})")
        logger.info(f"Estimated max RPS (theoretical): ~{estimated_max_rps:.1f} "
                    f"(with {max_users} concurrent workers)")
        logger.info("----------------------------------------\n")

        def _build_round_requests(target_rps, duration, request_pool):
            """根据目标 RPS 和时长，从请求池中采样并压缩到时间窗口内"""
            target_count = max(1, int(target_rps * duration))
            target_count = min(target_count, len(request_pool))

            sampled_indices = sorted(random.sample(range(len(request_pool)), target_count))
            sampled = [copy.deepcopy(request_pool[i]) for i in sampled_indices]

            # 将 timestamp 均匀分布在 [0, duration] 区间
            if len(sampled) > 1:
                for i, req in enumerate(sampled):
                    req["timestamp"] = (i / (len(sampled) - 1)) * duration
            elif len(sampled) == 1:
                sampled[0]["timestamp"] = 0.0

            return sampled

        # 二分搜索最大安全 RPS
        low_rps = min_rps
        high_rps = max_rps
        max_safe_rps = 0.0
        max_safe_concurrency = 0
        max_user_results = {}
        final_user_ttft_dict = defaultdict(list)
        final_user_tpot_dict = defaultdict(list)
        round_number = 0

        test_start_time = time.time()

        logger.info(f"Auto stress test: RPS range [{low_rps}, {high_rps}], "
                    f"precision={rps_precision}, round_duration={target_duration}s, "
                    f"safe_confirm={safe_confirm_rounds}")

        while (high_rps - low_rps) >= rps_precision:
            current_rps = round((low_rps + high_rps) / 2, 2)
            round_number += 1

            # 安全确认：同一 RPS 需连续通过 N 次才算安全
            confirm_pass = 0
            confirm_fail = False

            for confirm_idx in range(safe_confirm_rounds):
                sub_label = f" [{confirm_idx+1}/{safe_confirm_rounds}]" if safe_confirm_rounds > 1 else ""
                round_requests = _build_round_requests(current_rps, target_duration, all_scheduled)
                num_requests = len(round_requests)
                unique_users = set(r["user_id"] for r in round_requests)

                logger.info(f"\n--- Round {round_number}{sub_label}: target_rps={current_rps}, "
                            f"requests={num_requests}, users={len(unique_users)} ---")

                latency_tracker = LatencyTracker(window_seconds=window_size)
                scheduler = RealisticScheduler(
                    latency_tracker=latency_tracker,
                    inference_fn=lambda prompt, max_tokens=None, **kw: inference_fn(
                        prompt, 1.0, max_tokens=max_tokens),
                    max_workers=max_users,
                    speed_factor=speed_factor,
                )

                round_start = time.time()
                scheduler.start(round_requests)
                round_elapsed = time.time() - round_start

                # 检查是否因熔断提前终止
                circuit_broken = scheduler.is_circuit_broken()
                failure_rate = scheduler.get_failure_rate()

                state = sla_engine.check(
                    latency_tracker.get_ttft_window(),
                    latency_tracker.get_tpot_window())

                actual_rps = num_requests / round_elapsed if round_elapsed > 0 else 0
                peak_concurrency = scheduler.get_max_observed_concurrency()

                if circuit_broken:
                    logger.info(f"  Result: CIRCUIT_BREAK (failure_rate={failure_rate:.1%}), "
                                f"elapsed={round_elapsed:.1f}s, peak_concurrency={peak_concurrency}")
                    confirm_fail = True
                    break
                else:
                    logger.info(f"  Result: SLA={state}, elapsed={round_elapsed:.1f}s, "
                                f"actual_rps={actual_rps:.2f}, peak_concurrency={peak_concurrency}, "
                                f"failure_rate={failure_rate:.1%}")

                    if state in ("SAFE", "WARNING"):
                        confirm_pass += 1
                        # 保存指标（仅保留最后一次确认的数据）
                        final_user_ttft_dict_candidate = defaultdict(list)
                        final_user_tpot_dict_candidate = defaultdict(list)
                        for user_id, ttft, tpot in scheduler.get_user_metrics():
                            final_user_ttft_dict_candidate[user_id].append(ttft)
                            final_user_tpot_dict_candidate[user_id].append(tpot)
                    else:
                        confirm_fail = True
                        break

            # 判断结果
            if not confirm_fail and confirm_pass >= safe_confirm_rounds:
                logger.info(f"  ✓ RPS {current_rps} confirmed SAFE ({confirm_pass}/{safe_confirm_rounds})")
                max_safe_rps = current_rps
                max_safe_concurrency = peak_concurrency
                low_rps = current_rps + rps_precision
                final_user_ttft_dict = final_user_ttft_dict_candidate
                final_user_tpot_dict = final_user_tpot_dict_candidate
                max_user_results = analyze_users(
                    final_user_ttft_dict, final_user_tpot_dict, TTFT_LIMIT, TPOT_LIMIT)
            else:
                logger.info(f"  ✗ RPS {current_rps} FAILED (pass={confirm_pass}/{safe_confirm_rounds})")
                high_rps = current_rps - rps_precision

        test_end_time = time.time()

        # 最终报告
        logger.info("\n====================================")
        logger.info("Stress Test Complete")
        logger.info("====================================")
        logger.info(f"Max Safe RPS: {max_safe_rps}")
        logger.info(f"Peak Concurrency at Max Safe RPS: {max_safe_concurrency}")
        logger.info(f"Total rounds: {round_number}")
        logger.info(f"Total test time: {test_end_time - test_start_time:.1f}s "
                    f"({(test_end_time - test_start_time)/60:.1f}min)")

        if max_user_results:
            logger.info("\nUser-level Analysis (at max safe RPS):")
            for user, metrics in sorted(max_user_results.items()):
                logger.info(f"  User {user}: requests={metrics['requests']}, "
                            f"P99_TTFT={metrics['p99_ttft']}s, "
                            f"P90_TPOT={metrics['p90_tpot']}s, SLA={metrics['sla_status']}")

        analysis_path = os.path.join(BASE_DIR, "benchmark", "user_analysis.json")
        with open(analysis_path, "w") as f:
            json.dump(max_user_results, f, indent=4)
        logger.info(f"User analysis saved to {analysis_path}")

        report_trace_info = {
            "trace_file": trace_config.get("trace_file", ""),
            "total_records": len(all_scheduled),
            "total_sessions": len(set(r["user_id"] for r in all_scheduled)),
            "schedule_mode": "realistic_stress",
            "max_safe_rps": max_safe_rps,
            "round_duration": target_duration,
            "total_rounds": round_number,
        }

        generate_benchmark_report(
            user_ttft_dict=final_user_ttft_dict,
            user_tpot_dict=final_user_tpot_dict,
            max_safe_concurrency=max_safe_concurrency,
            total_rps=max_safe_rps,
            test_start_time=test_start_time,
            test_end_time=test_end_time,
            ttft_limit=TTFT_LIMIT,
            tpot_limit=TPOT_LIMIT,
            model_name=inference_config.get("model_name", "unknown"),
            inference_type=inference_type,
            trace_info=report_trace_info,
            user_results=max_user_results,
        )
        return

    # ============================================================
    # 经典模式（classic）：二分搜索最大安全并发
    # ============================================================
    logger.info("\nMode: CLASSIC (binary search for max concurrency)")

    low = 1
    high = max_users
    max_safe_concurrency = 0
    rps_total = 100
    max_user_results = {}
    estimated_rps = 0.0
    final_user_ttft_dict = defaultdict(list)
    final_user_tpot_dict = defaultdict(list)

    test_start_time = time.time()

    while low <= high:
        concurrency = (low + high) // 2
        logger.info(f"\nTesting concurrency: {concurrency}")

        num_trials = observe_windows
        trial_states = []
        trial_durations = []

        for trial in range(num_trials):
            latency_tracker = LatencyTracker(window_seconds=window_size)

            if use_trace and trace_loader:
                max_input_tok = trace_config.get("max_input_tokens")
                users = workload_builder.build_users_from_trace(
                    trace_loader, concurrency, max_input_tokens=max_input_tok)
            else:
                users = workload_builder.build_users(concurrency)

            thread_manager = ThreadManager(max_workers=concurrency)
            current_concurrency = concurrency
            scheduler = ConversationScheduler(
                thread_manager,
                latency_tracker,
                lambda prompt, cc=current_concurrency, **kwargs: inference_fn(prompt, cc, **kwargs)
            )

            rps_per_user = rps_total / concurrency

            start_trial_time = time.time()
            scheduler.start(users, rps=rps_per_user)
            end_trial_time = time.time()
            duration = end_trial_time - start_trial_time

            state = sla_engine.check(latency_tracker.get_ttft_window(),
                                     latency_tracker.get_tpot_window())

            trial_states.append(state)
            trial_durations.append(duration)

            thread_manager.shutdown()

        safe_count = trial_states.count("SAFE")
        if safe_count >= (num_trials // 2 + 1):
            max_safe_concurrency = concurrency
            low = concurrency + 1

            final_user_ttft_dict = defaultdict(list)
            final_user_tpot_dict = defaultdict(list)
            for user_id, ttft, tpot in scheduler.get_user_metrics():
                final_user_ttft_dict[user_id].append(ttft)
                final_user_tpot_dict[user_id].append(tpot)
            max_user_results = analyze_users(final_user_ttft_dict, final_user_tpot_dict, TTFT_LIMIT, TPOT_LIMIT)

            total_reqs = sum(len(ttfts) for ttfts in final_user_ttft_dict.values())
            estimated_rps = total_reqs / np.mean(trial_durations) if trial_durations else 0.0
        else:
            high = concurrency - 1

    test_end_time = time.time()

    logger.info("\n====================================")
    logger.info("User-level Analysis & Benchmark Summary")
    logger.info("====================================")
    for user, metrics in max_user_results.items():
        logger.info(f"User: {user}, Requests: {metrics['requests']}, "
                    f"P99 TTFT: {metrics['p99_ttft']}s, P90 TPOT: {metrics['p90_tpot']}s, SLA: {metrics['sla_status']}")

    logger.info(f"\nMax Stable Concurrency: {max_safe_concurrency}")
    logger.info(f"Estimated Throughput: ~{estimated_rps:.2f} RPS")

    analysis_path = os.path.join(BASE_DIR, "benchmark", "user_analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(max_user_results, f, indent=4)
    logger.info(f"User analysis saved to {analysis_path}")

    report_trace_info = None
    if use_trace and trace_loader:
        summary = trace_loader.summary()
        report_trace_info = {
            "trace_file": trace_config.get("trace_file", ""),
            "total_records": summary["total_records"],
            "total_sessions": summary["total_sessions"],
        }

    generate_benchmark_report(
        user_ttft_dict=final_user_ttft_dict,
        user_tpot_dict=final_user_tpot_dict,
        max_safe_concurrency=max_safe_concurrency,
        total_rps=rps_total,
        test_start_time=test_start_time,
        test_end_time=test_end_time,
        ttft_limit=TTFT_LIMIT,
        tpot_limit=TPOT_LIMIT,
        model_name=inference_config.get("model_name", "unknown"),
        inference_type=inference_type,
        trace_info=report_trace_info,
        user_results=max_user_results,
    )

if __name__ == "__main__":
    main()