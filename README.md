# LLM SLA Benchmark

基于真实 trace 数据的 LLM 推理服务压力测试工具，通过自动加压策略找到满足 SLA 约束的最大安全吞吐量。

## 项目概述

本工具解决的核心问题：**给定一个已部署的 LLM 推理服务和 SLA 指标要求，自动测出它能稳定承受的最大请求吞吐量（RPS）和并发数。**

### 核心特性

- **Trace 分布驱动负载**：基于 Kimi Mooncake (FAST'25) 开源 trace 数据，还原请求长度分布和用户行为模式
- **自动加压测试**：二分搜索算法自动逼近极限 RPS，无需人工调参
- **多次安全确认**：同一 RPS 需连续通过 N 次测试才确认为安全，消除随机波动
- **智能熔断机制**：失败率过高时自动终止当前轮，避免无效等待
- **429 退避重试**：指数退避策略处理服务端限流，不误判为性能问题
- **多维度报告**：生成 Markdown/JSON 报告，含延迟、吞吐、峰值并发和用户级 SLA 分析

## 运行原理

### 整体流程

```
┌─────────────────────────────────────────────────────────┐
│  1. 加载 Trace 数据 → 构建请求池                          │
│  2. 数据集深度分析（Token 分布、用户行为、前缀复用元数据）    │
│  3. 二分搜索循环：                                        │
│     ├─ 选定候选 RPS                                      │
│     ├─ 按 RPS 采样请求，均匀分布到时间窗口                 │
│     ├─ 并发执行推理请求                                   │
│     ├─ 收集 TTFT / TPOT 延迟指标                         │
│     ├─ SLA 引擎判定 SAFE / WARNING / VIOLATED            │
│     ├─ 安全确认（连续 N 次通过）                          │
│     └─ 二分调整搜索范围                                   │
│  4. 输出最终报告                                         │
└─────────────────────────────────────────────────────────┘
```

### 关键指标

| 指标 | 含义 | 典型阈值 |
|------|------|---------|
| **TTFT** (Time to First Token) | 首个 Token 的响应延迟 | P99 < 5000ms |
| **TPOT** (Time per Output Token) | 每个输出 Token 的生成间隔 | P90 < 200ms |
| **RPS** (Requests per Second) | 每秒请求数 | 越高越好 |

### 二分搜索算法

```
low_rps = 0.5, high_rps = 5.0, precision = 0.03

while (high - low) >= precision:
    candidate = (low + high) / 2
    
    # 连续 3 次确认
    for i in range(3):
        result = run_test(candidate)
        if result == VIOLATED:
            high = candidate - precision  # 降低上界
            break
    else:
        max_safe_rps = candidate
        low = candidate + precision       # 提高下界
```

## 数据来源

### Kimi Mooncake Trace (FAST'25)

数据来自论文 *"Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving"* (FAST 2025) 的开源 trace：

- **论文**：https://www.usenix.org/conference/fast25/presentation/qin-ruoyu
- **数据格式**：JSONL，每行一条请求记录

```json
{
    "timestamp": 1700000000,
    "input_length": 4096,
    "output_length": 356,
    "hash_ids": [123, 456, 789, ...]
}
```

| 字段 | 说明 |
|------|------|
| `timestamp` | 请求到达时间（Unix 秒） |
| `input_length` | 输入 Token 数 |
| `output_length` | 输出 Token 数 |
| `hash_ids` | KV Cache Block ID 列表，用于标识前缀复用关系 |

### 数据特征（默认 max_records=5000 时）

- 总记录数：5000
- 独立用户：2602
- 输入长度：中位数 4096 tokens，88.9% 在 1K~4K 范围
- 输出长度：中位数 356 tokens，57.7% 在 100~500 范围
- 对话轮数：70.6% 单轮、29.4% 多轮
- KV Cache 命中率：约 29.4%（多轮对话用户可复用前缀）

## 项目结构

```
llm-bench/
├── config/
│   ├── sla.yaml              # SLA 阈值配置
│   └── workload.yaml         # 负载和测试参数配置
├── data/
│   ├── prompt_templates.json # Prompt 模板库
├── FAST25-release/           # Kimi Mooncake trace 数据
│   └── traces/
│       └── conversation_trace.jsonl
├── benchmark/
│   ├── main.py               # 主入口，自动加压逻辑
│   ├── controller/
│   │   └── sla_engine.py     # SLA 判定引擎
│   ├── inference/
│   │   └── real_inference.py # 推理接口（含 429 退避重试）
│   ├── metrics/
│   │   └── latency_tracker.py # 延迟指标收集
│   ├── scheduler/
│   │   ├── realistic_scheduler.py  # 真实负载调度器（含熔断）
│   │   ├── conversation_scheduler.py
│   │   └── thread_manager.py
│   ├── workload/
│   │   ├── trace_loader.py   # Trace 数据加载与分析
│   │   ├── workload_builder.py # 请求构建
│   │   └── prompt_generator.py
│   └── utils/
│       ├── config_loader.py
│       └── logger.py
└── reports/                   # 自动生成的测试报告
    ├── *.md
    ├── *.json
```

## 快速开始

### 环境要求

- Python 3.8+
- 依赖：`requests`, `numpy`, `pyyaml`

```bash
pip install requests numpy pyyaml
```

### 配置

#### 1. SLA 阈值（`config/sla.yaml`）

```yaml
ttft_p99: 5.0         # P99 TTFT 上限（秒）
tpot_p90: 0.2         # P90 TPOT 上限（秒）
window_size: 60       # 统计窗口大小（秒）
observe_windows: 3    # 观察窗口数
min_samples: 5        # 进行 SLA 判定所需的最少有效样本数
```

#### 2. 负载配置（`config/workload.yaml`）

```yaml
# 调度模式: "classic"（固定并发）或 "realistic"（trace 分布驱动 RPS 压测）
schedule_mode: realistic

# 推理服务配置。默认 fake 可用于本地 smoke test；真实服务改为 vllm/ollama。
inference_type: fake   # vllm | ollama | fake
inference:
  base_url: "http://localhost:8000/v1"
  model_name: "your-model-name"
  api_key_env: "LLM_BENCH_API_KEY"
  timeout: 300
  max_tokens: 100

# 最大并发线程数（建议设为预期峰值并发的 2~3 倍）
max_users: 128

# 每轮测试时长（秒）
replay_duration_seconds: 120

# 自动加压参数
pressure:
  min_rps: 0.5            # RPS 搜索下界
  max_rps: 5.0            # RPS 搜索上界
  rps_precision: 0.03     # 搜索精度
  safe_confirm_rounds: 3  # 安全确认次数

# 熔断参数
circuit_breaker:
  failure_rate_threshold: 0.5
  min_requests: 20

# Trace 数据配置
trace_data:
  enabled: true
  trace_file: "FAST25-release/traces/conversation_trace.jsonl"
  max_records: 5000
  max_input_tokens: 4096
```

### 运行

```bash
cd benchmark
python main.py
```

也可以从仓库根目录运行：

```bash
python run_benchmark.py
```

### 测试

```bash
python -m unittest discover -s tests
```

### 输出

运行完成后，自动生成报告到 `reports/` 目录：

- `*.md` — Markdown 格式报告
- `*.json` — 结构化 JSON 数据

## 使用场景

### 场景 1：评估新模型部署的服务能力

```yaml
# 修改 workload.yaml 中的推理配置，并通过环境变量提供密钥
inference_type: vllm
inference:
  base_url: "http://new-model-service:8000/v1"
  model_name: "qwen3-72b"
  api_key_env: "LLM_BENCH_API_KEY"
```

### 场景 2：调整 SLA 阈值看容量变化

```yaml
# 放宽 TPOT 阈值，看吞吐能提升多少
tpot_p90: 0.3    # 从 200ms 放宽到 300ms
```

### 场景 3：快速粗测 vs 精细测试

```yaml
# 快速粗测（~10 分钟）
pressure:
  rps_precision: 0.1
  safe_confirm_rounds: 1

# 精细测试（~30 分钟）
pressure:
  rps_precision: 0.03
  safe_confirm_rounds: 3
```

### 场景 4：使用 fake 模式验证工具本身

```yaml
inference_type: fake   # 不需要真实推理服务，使用模拟延迟
```

## 测试结果示例

以下是 Qwen3-32B 单实例（vLLM 部署）的测试结果：

| 指标 | 值 |
|------|-----|
| Max Safe RPS | 0.76 |
| Peak Concurrency | 47 |
| Average TTFT | 1193.8ms |
| P99 TTFT | 1410.9ms |
| Average TPOT | 150.5ms |
| P90 TPOT | 203.1ms |
| Cache 命中率 | ~29.4% |
| 瓶颈 | TPOT（每 Token 生成速度） |

## 核心模块说明

| 模块 | 职责 |
|------|------|
| `trace_loader.py` | 加载 FAST'25 trace，按 hash_ids 前缀分组为会话，分析突发流量 |
| `realistic_scheduler.py` | 按时间表并发执行请求，含失败率熔断机制 |
| `real_inference.py` | 调用 OpenAI-compatible API，SSE 流式解析，含 429 指数退避重试 |
| `sla_engine.py` | 基于滑动窗口的 SLA 实时判定（SAFE / WARNING / VIOLATED） |
| `main.py` | 主控逻辑：数据集分析 → 二分搜索 → 多次确认 → 生成报告 |

## License

MIT