#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=app
streamlit run app/dashboard.py
