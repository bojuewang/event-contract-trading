#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p logs pids data/reports

API_PORT="${API_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"
PID_FILE="pids/dashboard.pid"
LOG_FILE="logs/dashboard.log"

echo "[09] 检查 API health"
if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
  echo "[09] API OK"
else
  echo "[WARN] API 未响应。若需要 dashboard 调 API，请先重跑阶段 03。"
fi

echo "[09] 启动/复用 Streamlit dashboard port=$DASHBOARD_PORT"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "[09] dashboard 已运行 pid=$(cat "$PID_FILE")"
else
  export PYTHONPATH=app
  nohup streamlit run app/dashboard.py --server.port "$DASHBOARD_PORT" --server.address 0.0.0.0 > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "[09] dashboard pid=$(cat "$PID_FILE"), log=$LOG_FILE"
fi

sleep 5
if curl -fsS "http://127.0.0.1:$DASHBOARD_PORT" >/dev/null 2>&1; then
  echo "[09] dashboard reachable: http://127.0.0.1:$DASHBOARD_PORT"
else
  echo "[WARN] dashboard 暂未响应，查看 logs/dashboard.log"
  tail -n 60 "$LOG_FILE" || true
fi

echo "[09] 检查模型和数据状态"
python - <<'PY'
from pathlib import Path
checks = {
    "model": Path("data/models/baseline_winprob.joblib").exists(),
    "backtest_metrics": Path("data/backtests/threshold_40_40_metrics.json").exists(),
    "gpu_report": Path("data/reports/gpu_monte_carlo_benchmark.json").exists(),
}
print(checks)
PY

echo "[09] Dashboard 阶段完成。"
