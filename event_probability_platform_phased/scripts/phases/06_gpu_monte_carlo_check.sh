#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/reports

echo "[06] nvidia-smi 检查"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
else
  echo "[06] 未发现 nvidia-smi；继续执行 PyTorch 检查。"
fi

echo "[06] PyTorch / CUDA smoke test"
PYTHONPATH=app python app/gpu_check.py || true

echo "[06] Monte Carlo benchmark"
PYTHONPATH=app python app/gpu_monte_carlo_benchmark.py --paths "${MC_BENCHMARK_PATHS:-200000}" --minutes 24 --out data/reports/gpu_monte_carlo_benchmark.json

echo "[06] GPU/Monte Carlo 阶段完成。"
