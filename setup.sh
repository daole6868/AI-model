#!/usr/bin/env bash
# Cài toàn bộ đồ chơi "weight programming" vào thư mục này.
#   ./setup.sh            # Gemma đã mod + neuron-explorer
#   ./setup.sh --qwen     # thêm Qwen3.5-0.8B đã sửa weight (1.7 GB)
#   ./setup.sh --qwen4b   # thêm Qwen3.5-4B (9.3 GB) để neuron-explorer chạy model trực tiếp
set -euo pipefail
cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "Cần cài uv trước: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }

# 1) Môi trường Python cho các script trong scripts/
[ -d .venv ] || uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt
HF=".venv/bin/hf"

# 2) Gemma-3-270M đã cấy 640 con số (0.5 GB)
$HF download Neeze/gemma-3-270m-it-vi-steer --local-dir models/gemma-3-270m-it-vi-steer

# 3) neuron-explorer
mkdir -p third_party
[ -d third_party/neuron-explorer/.git ] || \
  GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/lyramakesmusic/neuron-explorer third_party/neuron-explorer
(cd third_party/neuron-explorer && uv sync)

for arg in "$@"; do
  case "$arg" in
    --qwen)   $HF download RikiyaT/Qwen3.5-0.8B-weight-space-programming \
                --local-dir models/Qwen3.5-0.8B-weight-space-programming --exclude "eval/*" ;;
    --qwen4b) $HF download Qwen/Qwen3.5-4B ;;
  esac
done

echo "Xong. Xem README.md để biết cách chạy."
