#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/reports logs

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

echo "[13] 检查 Postgres / Redis 容器"
docker exec prob-postgres pg_isready -U prob -d probability >/dev/null
docker exec prob-redis redis-cli ping | grep -q PONG

TICK_COUNT=$(docker exec prob-postgres psql -U prob -d probability -Atc "select count(*) from event_ticks")
echo "[13] event_ticks count=$TICK_COUNT"
if (( TICK_COUNT <= 0 )); then
  echo "[ERROR] event_ticks 为空，请先运行 Phase 11/12。"
  exit 1
fi

echo "[13] 生成实时 fair probability 与 40/40 对冲信号快照"
export PYTHONPATH=app
python app/live_hedge_signals.py \
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
  --json-out data/reports/live_hedge_signals.json \
  --csv-out data/reports/live_hedge_signals.csv

echo "[13] 信号摘要"
python - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("data/reports/live_hedge_signals.json").read_text(encoding="utf-8"))
print(f"status={report['status']} events_seen={report['events_seen']} signals={len(report['signals'])}")
for item in report["signals"][:8]:
    print(
        f"{item['signal']}: {item['first_leg_outcome']} first={item['current_first_fair_prob']:.4f} "
        f"vs {item['opposite_outcome']} opp={item['current_opposite_fair_prob']:.4f} "
        f"hit={item['hit_probability']:.3f} ev={item['expected_pnl_per_contract']:.4f} "
        f"reasons={','.join(item['reasons'])}"
    )
PY

echo "[13] Phase 13 完成。"
