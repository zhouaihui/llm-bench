# 真实 LLM 推理接口
#
# 支持多种部署方式：
# 1. vLLM 本地部署
# 2. Ollama 本地部署
# 3. 远程 API 服务

import time
import requests
import json
from typing import Optional, Tuple

from utils.logger import logger


class RealInference:
    """真实 LLM 推理接口，支持 OpenAI 兼容 API（含远程服务）"""

    def __init__(self, base_url: str, model_name: str, timeout: int = 300,
                 api_key: Optional[str] = None, max_tokens: int = 100):
        """
        初始化真实推理接口

        Args:
            base_url: 推理服务地址，如 "http://localhost:8000/v1"
            model_name: 模型名称，如 "llama-3-8b"
            timeout: 请求超时时间（秒）
            api_key: API 鉴权密钥（可选，用于远程服务）
            max_tokens: 最大生成 Token 数
        """
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self.api_key = api_key
        self.max_tokens = max_tokens

    def _build_headers(self) -> dict:
        """构建请求 Headers"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def infer(self, prompt: str, max_tokens: Optional[int] = None) -> Tuple[float, float]:
        """
        执行真实推理（Chat Completions 格式），返回 (TTFT, TPOT)

        Args:
            prompt: 输入 Prompt
            max_tokens: 本次请求的最大生成 Token 数（None 则使用默认值）

        Returns:
            (ttft, tpot): 首 Token 延迟和每个 Token 生成延迟
        """
        start_time = time.time()

        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": effective_max_tokens,
            "temperature": 0.7,
            "stream": True
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._build_headers(),
                    timeout=self.timeout,
                    stream=True
                )

                if response.status_code == 429:
                    backoff = 2 ** attempt + time.time() % 1
                    time.sleep(backoff)
                    if attempt < max_retries - 1:
                        continue
                    return float("inf"), float("inf")

                response.raise_for_status()
                break

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return float("inf"), float("inf")
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1 and "429" in str(e):
                    time.sleep(2 ** attempt)
                    continue
                return float("inf"), float("inf")

        try:

            first_any_token_time = None
            last_any_token_time = None
            total_token_count = 0

            for raw_chunk in response.iter_lines():
                if not raw_chunk:
                    continue

                chunk_time = time.time()

                line = raw_chunk.decode("utf-8") if isinstance(raw_chunk, bytes) else raw_chunk
                line = line.strip()

                parsed_json = None
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        parsed_json = json.loads(data_str)
                    except json.JSONDecodeError:
                        pass
                else:
                    try:
                        parsed_json = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        pass

                if parsed_json is None:
                    continue

                choices = parsed_json.get("choices")
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta") or {}

                # 检测是否有任何有效 token（reasoning 或 content）
                has_token = False
                for field in ("content", "reasoning_content", "reasoning", "text"):
                    value = delta.get(field)
                    if value is not None and value != "":
                        has_token = True
                        break

                if not has_token:
                    top_text = choice.get("text")
                    if top_text is not None and top_text != "":
                        has_token = True

                if has_token:
                    total_token_count += 1
                    if first_any_token_time is None:
                        first_any_token_time = chunk_time
                    last_any_token_time = chunk_time

            # TTFT = 服务端首次响应延迟（第一个 token，不论 reasoning 还是 content）
            ttft = first_any_token_time - start_time if first_any_token_time else 0

            # TPOT = 所有 token 的平均生成间隔
            total_time = last_any_token_time - start_time if last_any_token_time else 0
            if total_token_count > 1 and ttft > 0:
                tpot = (total_time - ttft) / (total_token_count - 1)
            else:
                tpot = 0

            return ttft, tpot

        except requests.exceptions.Timeout:
            logger.warning(f"Request timeout for prompt: {prompt[:50]}...")
            return float("inf"), float("inf")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error: {e}")
            return float("inf"), float("inf")


class OllamaInference:
    """Ollama 本地推理接口"""

    def __init__(self, model_name: str, timeout: int = 300):
        self.model_name = model_name
        self.timeout = timeout
        self.base_url = "http://localhost:11434/api"

    def infer(self, prompt: str, max_tokens: Optional[int] = None) -> Tuple[float, float]:
        start_time = time.time()

        effective_num_predict = max_tokens if max_tokens is not None else 100

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_predict": effective_num_predict
            }
        }

        try:
            response = requests.post(
                f"{self.base_url}/generate",
                json=payload,
                timeout=self.timeout,
                stream=True
            )

            response.raise_for_status()

            first_token_time = None
            last_token_time = None
            token_count = 0

            for chunk in response.iter_lines():
                if chunk:
                    chunk_time = time.time()
                    data = json.loads(chunk.decode("utf-8"))

                    if data.get("done"):
                        break

                    if data.get("response"):
                        token_count += 1
                        if first_token_time is None:
                            first_token_time = chunk_time
                        last_token_time = chunk_time

            ttft = first_token_time - start_time if first_token_time else 0
            total_time = last_token_time - start_time if last_token_time else 0

            if token_count > 1 and ttft > 0:
                tpot = (total_time - ttft) / (token_count - 1)
            else:
                tpot = 0

            return ttft, tpot

        except Exception as e:
            logger.warning(f"Ollama error: {e}")
            return float("inf"), float("inf")


def create_inference(inference_type: str, **kwargs):
    """
    工厂函数，创建推理接口

    Args:
        inference_type: "vllm" | "ollama" | "fake"
        **kwargs: 其他参数

    Returns:
        推理接口对象
    """
    if inference_type == "vllm":
        return RealInference(
            base_url=kwargs.get("base_url", "http://localhost:8000/v1"),
            model_name=kwargs.get("model_name", "llama-3-8b"),
            timeout=kwargs.get("timeout", 300),
            api_key=kwargs.get("api_key"),
            max_tokens=kwargs.get("max_tokens", 100)
        )
    elif inference_type == "ollama":
        return OllamaInference(
            model_name=kwargs.get("model_name", "llama3"),
            timeout=kwargs.get("timeout", 300)
        )
    else:
        # 返回 fake inference 函数
        import random
        def fake_inference(prompt, concurrency_factor=1.0, max_tokens=None):
            base_ttft = random.uniform(0.15, 0.4)
            base_tpot = random.uniform(0.02, 0.04)
            ttft = base_ttft * (1 + 0.05 * concurrency_factor)
            tpot = base_tpot * (1 + 0.05 * concurrency_factor)
            time.sleep(ttft * 0.1)
            return ttft, tpot
        return fake_inference
