#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/models data/reports

echo "[07] 训练 baseline win probability model"
export PYTHONPATH=app
python app/train_baseline.py | tee data/reports/train_baseline_metrics.txt

if [[ ! -f data/models/baseline_winprob.joblib ]]; then
  echo "[ERROR] 模型文件未生成：data/models/baseline_winprob.joblib"
  exit 1
fi

python - <<'PY'
from pathlib import Path
p = Path("data/models/baseline_winprob.joblib")
print(f"[07] model saved: {p} size_bytes={p.stat().st_size}")
PY

echo "[07] 训练阶段完成。"
