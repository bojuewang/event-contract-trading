#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=app
python app/ingest_odds.py
