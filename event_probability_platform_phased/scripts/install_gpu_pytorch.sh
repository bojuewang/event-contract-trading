#!/usr/bin/env bash
set -euo pipefail
# Always verify the right command at https://pytorch.org/get-started/locally/
# For many current NVIDIA systems, a CUDA wheel index like cu128 may be appropriate, but this can change.
CUDA_INDEX_URL="${PYTORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
python -m pip install --upgrade pip
pip install torch torchvision torchaudio --index-url "${CUDA_INDEX_URL}"
python app/gpu_check.py
