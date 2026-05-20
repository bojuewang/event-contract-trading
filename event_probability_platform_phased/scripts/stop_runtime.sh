#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for name in api dashboard ingest_odds; do
  pid_file="pids/${name}.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "stopping $name pid=$pid"
      kill "$pid" || true
    fi
    rm -f "$pid_file"
  fi
done
