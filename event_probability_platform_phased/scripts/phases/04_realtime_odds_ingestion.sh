#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p logs pids data/reports

set -a
[[ -f .env ]] && source .env
set +a

KEY="${ODDS_API_KEY:-}"
if [[ -z "$KEY" || "$KEY" == "replace_me" || "$KEY" == "你的_the_odds_api_key" ]]; then
  echo "[04] 未设置 ODDS_API_KEY，执行本地 dry-run，不调用外部 API。"
  PYTHONPATH=app python - <<'PY'
from ingest_odds import transform_odds_response
sample = [{
    "id": "sample-cavs-knicks",
    "home_team": "New York Knicks",
    "away_team": "Cleveland Cavaliers",
    "commence_time": "2026-05-19T23:00:00Z",
    "bookmakers": [{
        "key": "demo_book",
        "title": "Demo Book",
        "last_update": "2026-05-19T23:10:00Z",
        "markets": [{"key": "h2h", "outcomes": [
            {"name": "Cleveland Cavaliers", "price": 2.50},
            {"name": "New York Knicks", "price": 1.67}
        ]}]
    }]
}]
rows = transform_odds_response(sample, "decimal")
for row in rows:
    print(row)
print(f"[04] dry-run rows={len(rows)}")
PY
  echo "[04] dry-run 完成。填入 .env 的 ODDS_API_KEY 后可重跑本阶段。"
  exit 0
fi

PID_FILE="pids/ingest_odds.pid"
LOG_FILE="logs/ingest_odds.log"

echo "[04] 启动实时赔率采集 worker"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "[04] worker 已运行 pid=$(cat "$PID_FILE")"
else
  export PYTHONPATH=app
  nohup python app/ingest_odds.py > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "[04] worker pid=$(cat "$PID_FILE"), log=$LOG_FILE"
fi

sleep 8
echo "[04] 采集日志 tail"
tail -n 30 "$LOG_FILE" || true

echo "[04] 检查数据库最近 ticks 数量"
PYTHONPATH=app python - <<'PY'
from config import get_settings
from sqlalchemy import create_engine, text
s = get_settings()
engine = create_engine(s.database_url)
with engine.connect() as conn:
    n = conn.execute(text("select count(*) from event_ticks")).scalar()
print(f"[04] event_ticks count={n}")
PY

echo "[04] 实时采集阶段完成。"
