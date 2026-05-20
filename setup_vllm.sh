#!/bin/bash
# ============================================
# vLLM 环境搭建脚本
# 适用于：Alibaba Cloud Linux 3 + Tesla T4
# ============================================

set -e

echo "============================================"
echo "Step 1: 修复 NumPy 版本兼容问题"
echo "============================================"
pip install "numpy<2" -q
echo "NumPy 安装完成: $(python3 -c 'import numpy; print(numpy.__version__)')"

echo ""
echo "============================================"
echo "Step 2: 安装 vLLM"
echo "============================================"
pip install vllm -q
echo "vLLM 安装完成: $(python3 -c 'import vllm; print(vllm.__version__)')"

echo ""
echo "============================================"
echo "Step 3: 验证 GPU 环境"
echo "============================================"
python3 -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'Memory: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB')
"

echo ""
echo "============================================"
echo "Step 4: 下载并启动模型"
echo "============================================"
echo "Tesla T4 (16GB) 推荐使用以下模型："
echo "  - Qwen/Qwen2.5-1.5B (约 3GB 显存)"
echo "  - Qwen/Qwen2.5-3B   (约 6GB 显存)"
echo "  - Qwen/Qwen2.5-7B   (约 14GB 显存，需 half 精度)"
echo ""
echo "启动命令（选择一个执行）："
echo ""
echo "  # 小模型（推荐先用这个测试）"
echo "  vllm serve Qwen/Qwen2.5-1.5B --host 0.0.0.0 --port 8000 --max-model-len 2048"
echo ""
echo "  # 中等模型"
echo "  vllm serve Qwen/Qwen2.5-3B --host 0.0.0.0 --port 8000 --max-model-len 2048"
echo ""
echo "  # 7B 模型（需要 half 精度以适配 16GB 显存）"
echo "  vllm serve Qwen/Qwen2.5-7B --host 0.0.0.0 --port 8000 --max-model-len 2048 --dtype half --gpu-memory-utilization 0.9"
echo ""
echo "============================================"
echo "环境搭建完成！请选择上面的启动命令启动模型。"
echo "============================================"
