#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/reports data/paper_positions logs pids

API_PORT="${API_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"
API_PID_FILE="pids/api.pid"
DASHBOARD_PID_FILE="pids/dashboard.pid"
API_LOG="logs/api.log"
DASHBOARD_LOG="logs/dashboard.log"

echo "[17] 检查输入报告"
for path in data/reports/live_hedge_signals.json data/reports/risk_status.json; do
  if [[ ! -f "$path" ]]; then
    echo "[ERROR] 缺少 $path，请先运行 Phase 14/16。"
    exit 1
  fi
done

echo "[17] 生成/更新纸面持仓追踪报告"
export PYTHONPATH=app
python app/paper_position_tracker.py \
  --bootstrap-user-example \
  --positions data/paper_positions/open_positions.json \
  --signals data/reports/live_hedge_signals.json \
  --risk data/reports/risk_status.json \
  --json-out data/reports/paper_position_status.json \
  --csv-out data/reports/paper_position_status.csv

echo "[17] 重启 API 加载 /paper/positions"
if [[ -f "$API_PID_FILE" ]] && kill -0 "$(cat "$API_PID_FILE")" >/dev/null 2>&1; then
  kill "$(cat "$API_PID_FILE")" || true
  rm -f "$API_PID_FILE"
  sleep 1
fi
nohup uvicorn api:app --host 0.0.0.0 --port "$API_PORT" > "$API_LOG" 2>&1 &
echo $! > "$API_PID_FILE"

for i in {1..40}; do
  if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    echo "[17] API health OK"
    break
  fi
  if [[ "$i" == "40" ]]; then
    echo "[ERROR] API health 失败"
    tail -n 80 "$API_LOG" || true
    exit 1
  fi
  sleep 0.5
done

curl -fsS "http://127.0.0.1:$API_PORT/paper/positions" > data/reports/api_paper_positions_probe.json

echo "[17] 重启 dashboard 加载纸面持仓面板"
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
    echo "[17] dashboard reachable: http://127.0.0.1:$DASHBOARD_PORT"
    break
  fi
  if [[ "$i" == "40" ]]; then
    echo "[ERROR] dashboard 不可达"
    tail -n 80 "$DASHBOARD_LOG" || true
    exit 1
  fi
  sleep 0.5
done

echo "[17] 纸面持仓摘要"
python - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("data/reports/paper_position_status.json").read_text(encoding="utf-8"))
print(f"status={report['status']} mode={report['mode']} auto_trading_enabled={report['auto_trading_enabled']}")
print(f"positions={report['positions_evaluated']} ready={report['ready_second_legs']} high_hit={report['high_hit_watchlist']} blocked={report['blocked_positions']}")
for item in report["positions"]:
    print(
        f"{item['action']}: {item['first_leg_outcome']} @ {item['first_leg_price']:.2f} -> "
        f"{item['opposite_outcome']} target {item['opposite_target_price']:.2f}; "
        f"current_opposite={item.get('current_opposite_fair_prob', 0):.4f} "
        f"hit={item.get('hit_probability', 0):.3f} "
        f"mark_pnl={item.get('mark_pnl_if_unhedged_now', 0):.4f}"
    )
PY

echo "[17] Phase 17 完成。"
