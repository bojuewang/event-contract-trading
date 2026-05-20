#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"

echo "[01] 创建/复用 Python 虚拟环境 .venv"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

echo "[01] 安装 requirements.txt"
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[01] 已创建 .env；请稍后填入 ODDS_API_KEY。"
else
  echo "[01] .env 已存在，不覆盖。"
fi

echo "[01] 验证核心包导入"
PYTHONPATH=app python - <<'PY'
import fastapi, httpx, numpy, pandas, sqlalchemy, sklearn, streamlit, joblib
from odds_math import hedge_lock_profit, simulate_threshold_hit_probability
print("[01] imports OK")
print("[01] hedge sample", hedge_lock_profit(0.40, 0.40).__dict__)
print("[01] threshold sample", simulate_threshold_hit_probability(0.60, 0.40, 12, n_paths=1000, seed=1)["hit_probability"])
PY

echo "[01] 环境安装完成。"
