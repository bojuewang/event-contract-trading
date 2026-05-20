#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo "用法: scripts/confirm_phase.sh <phase_id> <token>"
  echo "示例: scripts/confirm_phase.sh 00_preflight CONFIRM-00_preflight-abcd1234"
  exit 2
fi
python3 phase_runner.py confirm "$1" --token "$2"
