#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p logs pids

PORT="${API_PORT:-8000}"
PID_FILE="pids/api.pid"
LOG_FILE="logs/api.log"

echo "[03] 启动/复用 FastAPI 服务 port=$PORT"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "[03] API 已运行 pid=$(cat "$PID_FILE")"
else
  export PYTHONPATH=app
  nohup uvicorn api:app --host 0.0.0.0 --port "$PORT" > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "[03] API pid=$(cat "$PID_FILE"), log=$LOG_FILE"
fi

echo "[03] 等待 /health"
for i in {1..40}; do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "[03] API health OK"
    break
  fi
  if [[ "$i" == "40" ]]; then
    echo "[ERROR] API health 失败"
    tail -n 80 "$LOG_FILE" || true
    exit 1
  fi
  sleep 0.5
done

echo "[03] 测试锁利计算：骑士 0.40 + 尼克斯目标 0.40"
curl -fsS -X POST "http://127.0.0.1:$PORT/hedge/lock-profit" \
  -H "Content-Type: application/json" \
  -d '{"first_leg_price":0.40,"second_leg_target":0.40,"fee_per_contract":0.00}' | python -m json.tool

echo "[03] 测试阈值触达模拟：当前 0.60 目标 0.40"
curl -fsS -X POST "http://127.0.0.1:$PORT/simulate/threshold" \
  -H "Content-Type: application/json" \
  -d '{"current_prob":0.60,"target_prob":0.40,"minutes_remaining":24,"n_paths":5000,"seed":42}' | python -m json.tool

echo "[03] API 阶段完成。"
