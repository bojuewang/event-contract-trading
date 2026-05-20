#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"

echo "[02] 启动 Postgres / Redis"
docker compose up -d postgres redis

echo "[02] 等待 Postgres 就绪"
for i in {1..60}; do
  if docker exec prob-postgres pg_isready -U prob -d probability >/dev/null 2>&1; then
    echo "[02] Postgres ready"
    break
  fi
  if [[ "$i" == "60" ]]; then
    echo "[ERROR] Postgres 未就绪"
    docker logs prob-postgres --tail 80 || true
    exit 1
  fi
  sleep 1
done

echo "[02] 检查 Redis"
if docker exec prob-redis redis-cli ping | grep -q PONG; then
  echo "[02] Redis ready"
else
  echo "[ERROR] Redis ping 失败"
  exit 1
fi

echo "[02] 检查 event_ticks 表"
docker exec prob-postgres psql -U prob -d probability -c "\dt" | sed -n '1,20p'

echo "[02] 数据服务阶段完成。"
