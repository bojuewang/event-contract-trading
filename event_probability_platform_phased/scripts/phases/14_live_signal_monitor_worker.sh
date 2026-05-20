#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p logs pids data/reports data/alerts

INTERVAL_SECONDS="${SIGNAL_MONITOR_INTERVAL_SECONDS:-5}"
OBSERVE_SECONDS="${SIGNAL_MONITOR_OBSERVE_SECONDS:-20}"
WINDOW_MINUTES="${SIGNAL_WINDOW_MINUTES:-3}"
FIRST_LEG_PRICE="${FIRST_LEG_PRICE:-0.40}"
OPPOSITE_TARGET_PRICE="${OPPOSITE_TARGET_PRICE:-0.40}"
FEE_PER_CONTRACT="${FEE_PER_CONTRACT:-0.00}"
SLIPPAGE_PER_LEG="${SLIPPAGE_PER_LEG:-0.005}"
MINUTES_REMAINING="${SIGNAL_MINUTES_REMAINING:-36}"
VOL_PER_SQRT_MIN="${DEFAULT_VOL_PER_SQRT_MIN:-0.045}"
MEAN_REVERSION="${DEFAULT_MEAN_REVERSION:-0.05}"
N_PATHS="${MONTE_CARLO_PATHS:-20000}"
MIN_HIT_PROBABILITY="${SIGNAL_MIN_HIT_PROBABILITY:-0.15}"
ENTRY_TOLERANCE="${SIGNAL_ENTRY_TOLERANCE:-0.03}"
MAX_DATA_AGE_SECONDS="${SIGNAL_MAX_DATA_AGE_SECONDS:-30}"
PID_FILE="pids/live_signal_monitor.pid"
LOG_FILE="logs/live_signal_monitor.log"
JSON_OUT="data/reports/live_hedge_signals.json"
CSV_OUT="data/reports/live_hedge_signals.csv"
ALERTS_OUT="data/alerts/hedge_signal_alerts.jsonl"

echo "[14] 检查实时赔率采集 worker"
if [[ ! -f pids/ingest_odds.pid ]] || ! kill -0 "$(cat pids/ingest_odds.pid)" >/dev/null 2>&1; then
  echo "[ERROR] ingest_odds worker 未运行。请先重跑 Phase 12。"
  exit 1
fi

echo "[14] 检查 Postgres / Redis 容器"
docker exec prob-postgres pg_isready -U prob -d probability >/dev/null
docker exec prob-redis redis-cli ping | grep -q PONG

echo "[14] 启动/复用实时信号 monitor worker interval=${INTERVAL_SECONDS}s"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "[14] signal monitor 已运行 pid=$(cat "$PID_FILE")"
else
  export PYTHONPATH=app
  nohup python app/live_signal_monitor.py \
    --interval-seconds "$INTERVAL_SECONDS" \
    --window-minutes "$WINDOW_MINUTES" \
    --first-leg-price "$FIRST_LEG_PRICE" \
    --opposite-target-price "$OPPOSITE_TARGET_PRICE" \
    --fee-per-contract "$FEE_PER_CONTRACT" \
    --slippage-per-leg "$SLIPPAGE_PER_LEG" \
    --minutes-remaining "$MINUTES_REMAINING" \
    --vol-per-sqrt-min "$VOL_PER_SQRT_MIN" \
    --mean-reversion "$MEAN_REVERSION" \
    --n-paths "$N_PATHS" \
    --min-hit-probability "$MIN_HIT_PROBABILITY" \
    --entry-tolerance "$ENTRY_TOLERANCE" \
    --max-data-age-seconds "$MAX_DATA_AGE_SECONDS" \
    --json-out "$JSON_OUT" \
    --csv-out "$CSV_OUT" \
    --alerts-out "$ALERTS_OUT" \
    > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "[14] signal monitor pid=$(cat "$PID_FILE"), log=$LOG_FILE"
fi

echo "[14] 观察 ${OBSERVE_SECONDS}s，确认信号文件持续刷新"
BEFORE_MTIME=0
if [[ -f "$JSON_OUT" ]]; then
  BEFORE_MTIME=$(stat -c %Y "$JSON_OUT")
fi
sleep "$OBSERVE_SECONDS"
AFTER_MTIME=0
if [[ -f "$JSON_OUT" ]]; then
  AFTER_MTIME=$(stat -c %Y "$JSON_OUT")
fi

if (( AFTER_MTIME <= BEFORE_MTIME )); then
  echo "[ERROR] 观察窗口内 $JSON_OUT 未刷新。"
  tail -n 80 "$LOG_FILE" || true
  exit 1
fi

echo "[14] signal monitor 日志 tail:"
tail -n 40 "$LOG_FILE" || true

echo "[14] 最新信号报告摘要"
python - <<'PY'
import json
from pathlib import Path

report_path = Path("data/reports/live_hedge_signals.json")
alerts_path = Path("data/alerts/hedge_signal_alerts.jsonl")
report = json.loads(report_path.read_text(encoding="utf-8"))
print(f"status={report['status']} generated_at={report['generated_at']} events_seen={report['events_seen']} signals={len(report['signals'])}")
print(f"paper_trade_candidates={sum(1 for s in report['signals'] if s['signal'] == 'paper_trade_candidate')}")
print(f"alerts_path={alerts_path} alerts_lines={sum(1 for _ in alerts_path.open(encoding='utf-8')) if alerts_path.exists() else 0}")
for item in report["signals"][:6]:
    print(
        f"{item['signal']}: {item['first_leg_outcome']} -> {item['opposite_outcome']} "
        f"hit={item['hit_probability']:.3f} ev={item['expected_pnl_per_contract']:.4f} "
        f"age={item['latest_age_seconds']:.1f}s"
    )
PY

echo "[14] Phase 14 完成。"
