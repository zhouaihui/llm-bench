"""诊断脚本：查看远程 API 流式响应的原始格式"""
import requests
import json
import time

url = "https://llmsecret-serving.cloud.misuan.com/serving/svmzyksabjdoxlig/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer ywkwsjmndbrkxlsarlutmiimzphrcsyi"
}
payload = {
    "model": "test_qwen3_32b",
    "messages": [{"role": "user", "content": "Say hello in one sentence"}],
    "stream": True,
    "max_tokens": 20
}

print("=== Sending request ===")
start = time.time()

response = requests.post(url, json=payload, headers=headers, timeout=300, stream=True)
print(f"Status: {response.status_code}")
print(f"Response headers: {dict(response.headers)}")
print(f"\n=== Raw chunks (first 20) ===")

chunk_count = 0
for line in response.iter_lines():
    if line:
        chunk_time = time.time() - start
        raw = line.decode("utf-8")
        print(f"[{chunk_time:.3f}s] RAW: {repr(raw)}")

        if raw.startswith("data: "):
            data = raw[6:]
            if data.strip() != "[DONE]":
                try:
                    parsed = json.loads(data)
                    choices = parsed.get("choices", [])
                    if choices:
                        choice = choices[0]
                        print(f"         KEYS in choice: {list(choice.keys())}")
                        delta = choice.get("delta", {})
                        text = choice.get("text", "")
                        content = delta.get("content", "")
                        print(f"         delta={delta}, text={repr(text)}, content={repr(content)}")
                except json.JSONDecodeError as e:
                    print(f"         JSON parse error: {e}")

    chunk_count += 1
    if chunk_count > 20:
        print("... (truncated)")
        break

print(f"\nTotal time: {time.time() - start:.3f}s")
