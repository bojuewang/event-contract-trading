#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"

mkdir -p logs pids data/models data/reports data/historical_odds data/backtests

echo "[00] 项目目录: $ROOT"
echo "[00] 当前时间: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "[00] 检查 Python"
python3 --version

PY_MAJ_MIN=$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
echo "[00] Python major.minor = $PY_MAJ_MIN"
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 需要 >= 3.10")
print("[00] Python 版本 OK")
PY

echo "[00] 检查 Docker / Docker Compose"
if command -v docker >/dev/null 2>&1; then
  docker --version
  if docker compose version >/dev/null 2>&1; then
    docker compose version
  else
    echo "[WARN] docker compose 不可用；阶段 02 会失败，需先安装 Docker Compose。"
  fi
else
  echo "[WARN] docker 未安装；阶段 02 需要 Docker。"
fi

echo "[00] 检查 curl"
if command -v curl >/dev/null 2>&1; then
  curl --version | head -n 1
else
  echo "[WARN] curl 未安装；API 验证阶段建议安装。"
fi

echo "[00] 检查 GPU 可见性"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
else
  echo "[INFO] 当前 shell 未发现 nvidia-smi。GPU 阶段会继续做 torch 检查。"
fi

echo "[00] 检查 .env"
if [[ -f .env ]]; then
  echo "[00] 已存在 .env"
else
  echo "[00] 尚无 .env；阶段 01 会从 .env.example 创建。"
fi

echo "[00] 阶段门控文件位置: .phase_state.json"
echo "[00] 预检查完成。"
