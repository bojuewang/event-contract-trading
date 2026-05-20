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
  echo "[ERROR] ODDS_API_KEY 未配置，无法启动真实实时采集 worker。"
  exit 2
fi

PID_FILE="pids/ingest_odds.pid"
LOG_FILE="logs/ingest_odds.log"
OBSERVE_SECONDS="${LIVE_INGEST_OBSERVE_SECONDS:-20}"

echo "[12] 检查 Postgres / Redis 容器"
docker exec prob-postgres pg_isready -U prob -d probability >/dev/null
docker exec prob-redis redis-cli ping | grep -q PONG

BEFORE=$(docker exec prob-postgres psql -U prob -d probability -Atc "select count(*) from event_ticks")
echo "[12] event_ticks before=$BEFORE"

echo "[12] 启动/复用真实赔率采集 worker"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "[12] worker 已运行 pid=$(cat "$PID_FILE")"
else
  export PYTHONPATH=app
  nohup python app/ingest_odds.py > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "[12] worker pid=$(cat "$PID_FILE"), log=$LOG_FILE"
fi

echo "[12] 观察 ${OBSERVE_SECONDS}s，确认实时 ticks 持续写入"
sleep "$OBSERVE_SECONDS"

AFTER=$(docker exec prob-postgres psql -U prob -d probability -Atc "select count(*) from event_ticks")
echo "[12] event_ticks after=$AFTER"

if (( AFTER <= BEFORE )); then
  echo "[ERROR] 观察窗口内 event_ticks 没有增长。"
  echo "[12] worker 日志 tail:"
  tail -n 80 "$LOG_FILE" || true
  exit 1
fi

echo "[12] worker 日志 tail:"
tail -n 40 "$LOG_FILE" || true

echo "[12] 生成实时采集状态报告"
export PYTHONPATH=app
python app/live_ingestion_check.py --report data/reports/live_ingestion_worker_report.json

echo "[12] Phase 12 完成。"
