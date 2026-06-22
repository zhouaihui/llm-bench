# 真实 LLM 推理负载测试指南

## 概述

现在 llm-bench 支持对接真实的 LLM 推理服务，可以测量真实的 TTFT 和 TPOT 指标。

---

## 支持的推理后端

| 类型 | 说明 | 适用场景 |
|------|------|---------|
| **fake** | 模拟推理（默认） | 快速测试、开发调试 |
| **vllm** | vLLM 本地部署 | 高性能推理服务 |
| **ollama** | Ollama 本地部署 | 简单易用的本地模型 |

---

## 方案一：使用 vLLM 部署

### 1. 安装 vLLM

```bash
pip install vllm
```

### 2. 启动 vLLM 服务

```bash
# 使用 llama-3-8b 模型
vllm serve meta-llama/Meta-Llama-3-8B \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9
```

### 3. 配置 workload.yaml

```yaml
# 负载模拟参数配置
max_users: 200
conversation_rounds: [3,10]
prompt_length: [50,500]
user_arrival_rate: poisson

# 推理配置
inference_type: vllm

inference:
  base_url: "http://localhost:8000/v1"
  model_name: "meta-llama/Meta-Llama-3-8B"
  api_key_env: "LLM_BENCH_API_KEY"
  timeout: 300
```

### 4. 运行 Benchmark

```bash
cd llm-bench/benchmark
python main.py
```

---

## 方案二：使用 Ollama 部署

### 1. 安装 Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows
# 从 https://ollama.com/download 下载安装包
```

### 2. 拉取模型

```bash
# 拉取 llama3 模型
ollama pull llama3

# 或其他模型
ollama pull llama3.1
ollama pull mistral
ollama pull codellama
```

### 3. 启动 Ollama 服务

```bash
# Ollama 默认在后台运行，端口 11434
ollama serve
```

### 4. 配置 workload.yaml

```yaml
# 负载模拟参数配置
max_users: 200
conversation_rounds: [3,10]
prompt_length: [50,500]
user_arrival_rate: poisson

# 推理配置
inference_type: ollama

inference:
  model_name: "llama3"
  timeout: 300
```

### 5. 运行 Benchmark

```bash
cd llm-bench/benchmark
python main.py
```

---

## 方案三：使用其他 API 服务

如果你有自己的 LLM API 服务（如 OpenAI 兼容接口），可以修改 `real_inference.py` 添加新的推理类。

```python
class YourCustomInference:
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    def infer(self, prompt: str) -> Tuple[float, float]:
        # 实现你的推理逻辑
        pass
```

---

## 配置参数说明

### workload.yaml

| 参数 | 说明 | 示例 |
|------|------|------|
| `inference_type` | 推理类型 | `"fake"` / `"vllm"` / `"ollama"` |
| `inference.base_url` | vLLM 服务地址 | `"http://localhost:8000/v1"` |
| `inference.model_name` | 模型名称 | `"llama-3-8b"` / `"llama3"` |
| `inference.timeout` | 请求超时时间（秒） | `300` |
| `inference.api_key_env` | API key 环境变量名（可选） | `"LLM_BENCH_API_KEY"` |

### sla.yaml

| 参数 | 说明 | 示例 |
|------|------|------|
| `ttft_p99` | P99 TTFT 阈值（秒） | `5.0` |
| `tpot_p90` | P90 TPOT 阈值（秒） | `0.2` |
| `window_size` | 滑动窗口大小（秒） | `60` |
| `observe_windows` | 每轮测试次数 | `3` |
| `min_samples` | SLA 判定前需要的最少有效样本数 | `5` |

---

## 运行示例

### 使用模拟推理（默认）

```bash
cd llm-bench/benchmark
python main.py
```

输出：
```
[INFO] Using fake inference (simulation mode)
[INFO] Testing concurrency: 100
[INFO] Testing concurrency: 150
...
[INFO] Max Stable Concurrency: 128
[INFO] Estimated Throughput: ~85.30 RPS
```

### 使用 vLLM 真实推理

```bash
# 1. 启动 vLLM
vllm serve meta-llama/Meta-Llama-3-8B --port 8000

# 2. 运行 Benchmark
cd llm-bench/benchmark
python main.py
```

输出：
```
[INFO] Using vllm inference: {'base_url': 'http://localhost:8000/v1', 'model_name': 'meta-llama/Meta-Llama-3-8B', 'api_key': '***REDACTED***'}
[INFO] Testing concurrency: 100
[INFO] Testing concurrency: 150
...
[INFO] Max Stable Concurrency: 64
[INFO] Estimated Throughput: ~45.20 RPS
```

---

## 注意事项

1. **GPU 资源**：真实推理需要 GPU 资源，确保 GPU 显存足够
2. **并发限制**：真实推理的并发能力受限于 GPU 和模型大小
3. **超时设置**：根据模型大小调整 `timeout` 参数
4. **网络延迟**：如果推理服务在远程，网络延迟会影响结果
5. **模型预热**：首次运行可能较慢，建议先预热模型

---

## 故障排查

### 问题：连接超时

```
Request timeout for prompt: ...
```

**解决**：
- 检查推理服务是否正常运行
- 增加 `timeout` 参数
- 检查网络连接

### 问题：显存不足

```
CUDA out of memory
```

**解决**：
- 减少 `max_users` 并发数
- 使用更小的模型
- 增加 `--gpu-memory-utilization` 参数

### 问题：请求失败

```
Request error: Connection refused
```

**解决**：
- 检查 `base_url` 是否正确
- 确认推理服务端口是否开放
