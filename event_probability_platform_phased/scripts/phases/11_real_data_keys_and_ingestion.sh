#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/reports logs

set -a
[[ -f .env ]] && source .env
set +a

KEY="${ODDS_API_KEY:-}"
REPORT="data/reports/real_data_ingestion_report.json"

echo "[11] 真实数据源接入检查"
if [[ -z "$KEY" || "$KEY" == "replace_me" || "$KEY" == "你的_the_odds_api_key" ]]; then
  echo "[ERROR] ODDS_API_KEY 未配置，Phase 11 不能使用 dry-run 通过。"
  echo "[11] 请编辑 .env，设置真实 ODDS_API_KEY 后重跑："
  echo "     python3 phase_runner.py run 11_real_data_keys_and_ingestion --rerun"
  PYTHONPATH=app python app/real_data_probe.py --report "$REPORT" || true
  exit 2
fi

echo "[11] 检查 Postgres / Redis 容器"
docker exec prob-postgres pg_isready -U prob -d probability >/dev/null
docker exec prob-redis redis-cli ping | grep -q PONG

echo "[11] 调用 The Odds API 并写入 event_ticks"
export PYTHONPATH=app
python app/real_data_probe.py --report "$REPORT"

echo "[11] 真实数据接入报告"
python -m json.tool "$REPORT"
echo "[11] Phase 11 完成。"
