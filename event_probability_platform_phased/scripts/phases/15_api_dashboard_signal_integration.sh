#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p logs pids data/reports

API_PORT="${API_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"
API_PID_FILE="pids/api.pid"
DASHBOARD_PID_FILE="pids/dashboard.pid"
API_LOG="logs/api.log"
DASHBOARD_LOG="logs/dashboard.log"
REPORT="data/reports/api_dashboard_signal_integration_report.json"

echo "[15] 检查信号报告文件"
if [[ ! -f data/reports/live_hedge_signals.json ]]; then
  echo "[ERROR] 缺少 data/reports/live_hedge_signals.json，请先运行 Phase 13/14。"
  exit 1
fi

echo "[15] 重启 FastAPI 以加载 /signals/live 与 /alerts/recent"
if [[ -f "$API_PID_FILE" ]] && kill -0 "$(cat "$API_PID_FILE")" >/dev/null 2>&1; then
  kill "$(cat "$API_PID_FILE")" || true
  rm -f "$API_PID_FILE"
  sleep 1
fi
export PYTHONPATH=app
nohup uvicorn api:app --host 0.0.0.0 --port "$API_PORT" > "$API_LOG" 2>&1 &
echo $! > "$API_PID_FILE"
echo "[15] API pid=$(cat "$API_PID_FILE")"

echo "[15] 等待 API health"
for i in {1..40}; do
  if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    echo "[15] API health OK"
    break
  fi
  if [[ "$i" == "40" ]]; then
    echo "[ERROR] API health 失败"
    tail -n 80 "$API_LOG" || true
    exit 1
  fi
  sleep 0.5
done

echo "[15] 验证 signals / alerts endpoints"
curl -fsS "http://127.0.0.1:$API_PORT/signals/live" > data/reports/api_signals_live_probe.json
curl -fsS "http://127.0.0.1:$API_PORT/alerts/recent?limit=5" > data/reports/api_alerts_recent_probe.json

python - <<'PY'
import json
from pathlib import Path

signals = json.loads(Path("data/reports/api_signals_live_probe.json").read_text(encoding="utf-8"))
alerts = json.loads(Path("data/reports/api_alerts_recent_probe.json").read_text(encoding="utf-8"))
print(f"[15] signals endpoint status={signals.get('status')} signals={len(signals.get('signals', []))}")
print(f"[15] alerts endpoint status={alerts.get('status')} count={alerts.get('count', 0)}")
if signals.get("status") != "ok":
    raise SystemExit("signals endpoint did not return ok")
PY

echo "[15] 重启 Streamlit dashboard 以加载信号面板"
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
echo "[15] dashboard pid=$(cat "$DASHBOARD_PID_FILE")"

echo "[15] 等待 dashboard"
for i in {1..40}; do
  if curl -fsS "http://127.0.0.1:$DASHBOARD_PORT" >/dev/null 2>&1; then
    echo "[15] dashboard reachable: http://127.0.0.1:$DASHBOARD_PORT"
    break
  fi
  if [[ "$i" == "40" ]]; then
    echo "[ERROR] dashboard 不可达"
    tail -n 80 "$DASHBOARD_LOG" || true
    exit 1
  fi
  sleep 0.5
done

python - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

signals = json.loads(Path("data/reports/api_signals_live_probe.json").read_text(encoding="utf-8"))
alerts = json.loads(Path("data/reports/api_alerts_recent_probe.json").read_text(encoding="utf-8"))
report = {
    "status": "ok",
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "api": {
        "health": "ok",
        "signals_status": signals.get("status"),
        "signals_count": len(signals.get("signals", [])),
        "alerts_status": alerts.get("status"),
        "alerts_count": alerts.get("count", 0),
    },
    "dashboard": {
        "url": "http://127.0.0.1:8501",
        "status": "reachable",
    },
}
Path("data/reports/api_dashboard_signal_integration_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, ensure_ascii=False, indent=2))
PY

echo "[15] Phase 15 完成。"
