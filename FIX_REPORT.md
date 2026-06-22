## llm-bench 项目问题修复报告

**修复时间**：2026-04-02  
**修复范围**：10 个文件，覆盖全部 5 个模块层

---

### 修复总览

| 序号 | 严重程度 | 文件 | 问题描述 | 修复状态 |
|------|---------|------|---------|---------|
| 1 | 🔴 严重 | `controller/sla_engine.py` | SLA 判断逻辑缺陷 + 空列表未防护 | ✅ 已修复 |
| 2 | 🔴 严重 | `controller/load_strategy.py` | BACKOFF 阶段无恢复逻辑，永久死锁 | ✅ 已修复 |
| 3 | 🔴 严重 | `scheduler/conversation_scheduler.py` | 多线程并发写入无锁保护 | ✅ 已修复 |
| 4 | 🔴 严重 | `workload/user_model.py` | `_id_counter` 非线程安全且不会重置 | ✅ 已修复 |
| 5 | 🟡 中等 | `benchmark/main.py` | 配置硬编码、变量作用域泄漏、线程池未关闭、lambda 闭包 bug | ✅ 已修复 |
| 6 | 🟡 中等 | `metrics/latency_tracker.py` | 未集成 SlidingWindow、窗口过期时机不一致 | ✅ 已修复 |
| 7 | 🟡 中等 | `metrics/sliding_window.py` | 缺少线程安全和主动过期清理 | ✅ 已修复 |
| 8 | 🟢 轻微 | `workload/workload_builder.py` | 对话轮数与配置文件不一致 | ✅ 已修复 |
| 9 | 🟢 轻微 | `scheduler/thread_manager.py` | 缺少 `shutdown()` 方法 | ✅ 已修复 |
| 10 | 🟢 轻微 | `data/prompt_templates.json` | 模板过少（仅 3 条） | ✅ 已修复 |
| 11 | 🟢 轻微 | `config/sla.yaml` | 阈值格式为字符串（`500ms`）而非数值 | ✅ 已修复 |

---

### 详细修复说明

#### 1. `controller/sla_engine.py` — SLA 判断逻辑修复

**问题**：
- TPOT 超标时只返回 `WARNING` 而非 `VIOLATED`，与 `main.py` 的判断逻辑矛盾
- 传入空列表时 `np.percentile` 会抛异常

**修复**：
- TTFT 或 TPOT 任一超标均返回 `VIOLATED`
- 新增 `WARNING` 阈值（90% 水位线预警）
- 添加空列表防护，空数据时返回 `SAFE`

```python
# 修复前
if p99 > self.ttft_limit:
    return "VIOLATED"
if p90 > self.tpot_limit:
    return "WARNING"      # ← TPOT 超标却只是 WARNING

# 修复后
if not ttft_values or not tpot_values:
    return "SAFE"
if p99_ttft > self.ttft_limit or p90_tpot > self.tpot_limit:
    return "VIOLATED"     # ← 任一超标即 VIOLATED
if p99_ttft > warning_ttft_threshold or p90_tpot > warning_tpot_threshold:
    return "WARNING"      # ← 90% 水位线预警
```

---

#### 2. `controller/load_strategy.py` — BACKOFF 恢复逻辑

**问题**：
- 进入 `BACKOFF` 阶段后没有任何恢复路径，永远停留在降级状态
- `RAMP_UP` 阶段未处理 `VIOLATED` 状态

**修复**：
- `BACKOFF` 阶段：SAFE/WARNING 时恢复到 `STABILIZE`
- `STABILIZE` 阶段：SAFE 时可重新进入 `RAMP_UP`
- 新增 `backoff_count` 计数器，连续多次 BACKOFF 后加大降级力度
- 新增 `reset()` 方法用于重置状态

---

#### 3. `scheduler/conversation_scheduler.py` — 线程安全修复

**问题**：
- `user_metrics`（`defaultdict(list)`）在多线程中并发写入，无锁保护
- 可能导致数据竞争和数据丢失

**修复**：
- 引入 `threading.Lock` 保护 `user_metrics` 的读写
- `run_user` 写入和 `get_user_metrics` 读取均加锁
- 移除未使用的 `ThreadPoolExecutor` 导入

```python
self._metrics_lock = threading.Lock()

# 写入加锁
with self._metrics_lock:
    self.user_metrics[user.id].append((ttft, tpot))

# 读取加锁
def get_user_metrics(self):
    with self._metrics_lock:
        ...
```

---

#### 4. `workload/user_model.py` — ID 计数器修复

**问题**：
- `_id_counter` 类变量在多轮测试中永远递增不重置
- `_id_counter += 1` 非原子操作

**修复**：
- 引入 `threading.Lock` 保护 ID 生成
- 新增 `reset_id_counter()` 类方法
- `WorkloadBuilder.build_users()` 每次构建前自动重置 ID

---

#### 5. `benchmark/main.py` — 多项修复

**问题与修复**：

| 子问题 | 修复方式 |
|--------|---------|
| SLA 阈值、并发上限等全部硬编码 | 使用 `config_loader.load_yaml()` 从 `sla.yaml` 和 `workload.yaml` 读取 |
| Prompt 模板路径 `"../data/..."` 依赖运行目录 | 使用 `BASE_DIR` + `os.path.join()` 构建绝对路径 |
| `user_ttft_dict` 在 SAFE 分支内定义，循环外引用可能 `UnboundLocalError` | 在循环前初始化 `final_user_ttft_dict` / `final_user_tpot_dict` |
| `lambda prompt: fake_inference(prompt, concurrency)` 闭包捕获变量引用 | 改为 `lambda prompt, cc=current_concurrency: fake_inference(prompt, cc)` |
| `ThreadManager` 未关闭，线程泄漏 | 每轮 trial 结束后调用 `thread_manager.shutdown()` |
| `num_trials` 硬编码为 3 | 使用配置中的 `observe_windows` |
| `window_seconds` 硬编码为 60 | 使用配置中的 `window_size` |
| 并发因子 `0.01` 太小，模拟不真实 | 调整为 `0.05`，`time.sleep` 改为与 TTFT 成比例 |
| 输出文件路径硬编码 | 使用 `os.path.join(BASE_DIR, ...)` |

---

#### 6. `metrics/latency_tracker.py` — 集成 SlidingWindow

**问题**：
- `LatencyTracker` 自己用 `deque` 实现了滑动窗口，`SlidingWindow` 类完全未被使用
- `_evict_old` 在多线程中不安全
- `get_ttft_window()` 和 `get_tpot_window()` 各自独立清理过期数据，窗口不一致

**修复**：
- 重构为使用 `SlidingWindow` 组件，消除重复实现
- 线程安全由 `SlidingWindow` 内部的锁保证
- 新增 `clear()` 方法

```python
# 修复后
class LatencyTracker:
    def __init__(self, window_seconds=60):
        self.ttft_window = SlidingWindow(window_size=window_seconds)
        self.tpot_window = SlidingWindow(window_size=window_seconds)

    def record(self, ttft, tpot):
        self.ttft_window.add(ttft)
        self.tpot_window.add(tpot)
```

---

#### 7. `metrics/sliding_window.py` — 线程安全增强

**问题**：
- 无锁保护，多线程并发 `add` 和 `values` 不安全
- `values()` 不会清理过期数据

**修复**：
- 引入 `threading.Lock`
- `add()` 和 `values()` 均加锁
- `values()` 调用前主动清理过期数据
- 新增 `clear()` 方法

---

#### 8. `workload/workload_builder.py` — 配置对齐

**问题**：
- 对话轮数硬编码为 `random.randint(3, 8)`，与 `workload.yaml` 中的 `[3, 10]` 不一致

**修复**：
- 构造函数接受 `conversation_rounds` 参数
- 从配置文件读取轮数范围
- 每次 `build_users()` 前自动重置 `User._id_counter`

---

#### 9. `scheduler/thread_manager.py` — 资源释放

**问题**：
- 缺少 `shutdown()` 方法，`ThreadPoolExecutor` 无法被正确关闭
- 每轮测试创建新线程池但不释放，导致线程泄漏

**修复**：
- 新增 `shutdown()` 方法，调用 `executor.shutdown(wait=True)`
- 移除重复的 `import` 语句

---

#### 10. `data/prompt_templates.json` — 模板扩充

**问题**：仅 3 条模板，长度差异小，无法模拟真实场景

**修复**：扩充至 **15 条**模板，覆盖不同长度和类型（解释、编码、翻译、设计、调试等）

---

#### 11. `config/sla.yaml` — 格式修复

**问题**：`ttft_p99: 500ms` 是字符串，`load_yaml` 解析后无法直接用于数值比较

**修复**：改为数值格式 `ttft_p99: 0.5`（单位：秒）

---

### 架构改进总结

修复后，项目实现了**设计与实现的统一**：

- ✅ **配置驱动**：所有参数从 YAML 配置文件加载，不再硬编码
- ✅ **模块复用**：`LatencyTracker` 正确集成 `SlidingWindow`，消除重复实现
- ✅ **线程安全**：所有多线程共享数据结构均有锁保护
- ✅ **资源管理**：线程池在每轮测试后正确关闭
- ✅ **路径安全**：所有文件路径使用 `os.path.join` + `BASE_DIR` 构建
- ✅ **完整状态机**：`LoadStrategy` 三阶段均有完整的状态转换逻辑
