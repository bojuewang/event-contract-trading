#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/reports

REPORT="data/reports/readiness_report.md"
API_PORT="${API_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"

API_STATUS="DOWN"
if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then API_STATUS="UP"; fi

DASH_STATUS="DOWN"
if curl -fsS "http://127.0.0.1:$DASHBOARD_PORT" >/dev/null 2>&1; then DASH_STATUS="UP"; fi

PG_STATUS="UNKNOWN"
if command -v docker >/dev/null 2>&1 && docker exec prob-postgres pg_isready -U prob -d probability >/dev/null 2>&1; then PG_STATUS="UP"; fi

REDIS_STATUS="UNKNOWN"
if command -v docker >/dev/null 2>&1 && docker exec prob-redis redis-cli ping 2>/dev/null | grep -q PONG; then REDIS_STATUS="UP"; fi

TICK_COUNT="N/A"
if [[ -d .venv ]]; then
  TICK_COUNT=$(PYTHONPATH=app python - <<'PY' 2>/dev/null || true
from config import get_settings
from sqlalchemy import create_engine, text
try:
    s = get_settings()
    engine = create_engine(s.database_url)
    with engine.connect() as conn:
        print(conn.execute(text("select count(*) from event_ticks")).scalar())
except Exception:
    print("N/A")
PY
)
fi

MODEL_STATUS="missing"
[[ -f data/models/baseline_winprob.joblib ]] && MODEL_STATUS="present"
BACKTEST_STATUS="missing"
[[ -f data/backtests/threshold_40_40_metrics.json ]] && BACKTEST_STATUS="present"
GPU_STATUS="missing"
[[ -f data/reports/gpu_monte_carlo_benchmark.json ]] && GPU_STATUS="present"

cat > "$REPORT" <<EOF2
# 实时事件概率预测平台：阶段化就绪报告

生成时间：$(date -u +'%Y-%m-%dT%H:%M:%SZ')

## 服务状态

| 项目 | 状态 |
|---|---|
| FastAPI | $API_STATUS |
| Dashboard | $DASH_STATUS |
| Postgres | $PG_STATUS |
| Redis | $REDIS_STATUS |
| event_ticks rows | $TICK_COUNT |

## 模型与回测状态

| 项目 | 状态 |
|---|---|
| baseline_winprob.joblib | $MODEL_STATUS |
| threshold_40_40_metrics.json | $BACKTEST_STATUS |
| gpu_monte_carlo_benchmark.json | $GPU_STATUS |

## 风控开关建议

- 数据延迟超过阈值：暂停信号。
- 没有订单簿深度或盘口断流：不输出可执行机会。
- second leg 目标价触达概率不足：只观察，不执行。
- fees + slippage 后净锁利 <= 0：禁止信号。
- 未完成历史回测和纸面交易：不做自动下单。

## 下一步生产化任务

1. 接入真实 WebSocket orderbook 数据源。
2. 用真实历史 odds snapshots + play-by-play 替换 dry-run 训练样例。
3. 将阈值触达模型从模拟过程升级为监督学习模型。
4. 加入 Telegram/Discord/Email alert。
5. 加入数据延迟、盘口异常、成交深度、模型置信度四类风控监控。
EOF2

cat "$REPORT"
echo "[10] readiness report saved: $REPORT"
echo "[10] 所有阶段脚本执行完成。"
