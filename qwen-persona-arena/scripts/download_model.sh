#!/usr/bin/env bash
# NOT run during setup (weights are ~16 GB). Run it yourself when ready, then point QWEN_MODEL at the folder.
#   bash scripts/download_model.sh [target_dir]
set -euo pipefail
DIR="${1:-$HOME/models/Qwen3-8B}"
uvx --from huggingface_hub hf download Qwen/Qwen3-8B --local-dir "$DIR"
echo "export QWEN_MODEL=$DIR"
