#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/reports logs pids

API_PORT="${API_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"
MAX_TICK_AGE_SECONDS="${RISK_MAX_TICK_AGE_SECONDS:-30}"
MAX_SIGNAL_AGE_SECONDS="${RISK_MAX_SIGNAL_AGE_SECONDS:-20}"
API_PID_FILE="pids/api.pid"
DASHBOARD_PID_FILE="pids/dashboard.pid"
API_LOG="logs/api.log"
DASHBOARD_LOG="logs/dashboard.log"

echo "[16] 生成实时风控状态"
export PYTHONPATH=app
python app/risk_status.py \
  --json-out data/reports/risk_status.json \
  --api-port "$API_PORT" \
  --dashboard-port "$DASHBOARD_PORT" \
  --max-tick-age-seconds "$MAX_TICK_AGE_SECONDS" \
  --max-signal-age-seconds "$MAX_SIGNAL_AGE_SECONDS" \
  --fail-on-blocked

echo "[16] 重启 API 加载 /risk/status"
if [[ -f "$API_PID_FILE" ]] && kill -0 "$(cat "$API_PID_FILE")" >/dev/null 2>&1; then
  kill "$(cat "$API_PID_FILE")" || true
  rm -f "$API_PID_FILE"
  sleep 1
fi
nohup uvicorn api:app --host 0.0.0.0 --port "$API_PORT" > "$API_LOG" 2>&1 &
echo $! > "$API_PID_FILE"

for i in {1..40}; do
  if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    echo "[16] API health OK"
    break
  fi
  if [[ "$i" == "40" ]]; then
    echo "[ERROR] API health 失败"
    tail -n 80 "$API_LOG" || true
    exit 1
  fi
  sleep 0.5
done

curl -fsS "http://127.0.0.1:$API_PORT/risk/status" > data/reports/api_risk_status_probe.json
python - <<'PY'
import json
from pathlib import Path

risk = json.loads(Path("data/reports/api_risk_status_probe.json").read_text(encoding="utf-8"))
print(f"[16] /risk/status status={risk.get('status')} checks={len(risk.get('checks', []))}")
if risk.get("status") == "blocked":
    raise SystemExit("risk status is blocked")
PY

echo "[16] 重启 Dashboard 加载风控面板"
if [[ -f "$DASHBOARD_PID_FILE" ]] && kill -0 "$(cat "$DASHBOARD_PID_FILE")" >/dev/null 2>&1; then
  kill "$(cat "$DASHBOARD_PID_FILE")" || true
  rm -f "$DASHBOARD_PID_FILE"
  sleep 1
fi
nohup streamlit run app/dashboard.py \
  --server.port "$DASHBOARD_PORT" \
  --server.address 0.0.0.0 \
  --server.headless true \
  --browser.gatherUsageStats false \
  > "$DASHBOARD_LOG" 2>&1 &
echo $! > "$DASHBOARD_PID_FILE"

for i in {1..40}; do
  if curl -fsS "http://127.0.0.1:$DASHBOARD_PORT" >/dev/null 2>&1; then
    echo "[16] dashboard reachable: http://127.0.0.1:$DASHBOARD_PORT"
    break
  fi
  if [[ "$i" == "40" ]]; then
    echo "[ERROR] dashboard 不可达"
    tail -n 80 "$DASHBOARD_LOG" || true
    exit 1
  fi
  sleep 0.5
done

echo "[16] 风控摘要"
python - <<'PY'
import json
from pathlib import Path
risk = json.loads(Path("data/reports/risk_status.json").read_text(encoding="utf-8"))
print(f"status={risk['status']} mode={risk['mode']} auto_trading_enabled={risk['auto_trading_enabled']}")
print(f"tick_age={risk['database'].get('latest_tick_age_seconds'):.2f}s signal_age={risk['signals'].get('report_age_seconds'):.2f}s")
print(f"warnings={len(risk['warning_checks'])} blocked={len(risk['blocked_checks'])}")
PY

echo "[16] Phase 16 完成。"
