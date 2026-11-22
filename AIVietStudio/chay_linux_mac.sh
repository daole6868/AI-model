#!/usr/bin/env bash
# AI Việt Studio - chạy trên Linux / macOS:  bash chay_linux_mac.sh
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  PY=$(command -v python3 || command -v python || true)
  if [ -z "$PY" ]; then
    echo "[LỖI] Không tìm thấy Python 3.10+. Hãy cài Python rồi chạy lại."; exit 1
  fi
  echo "[1/3] Tạo môi trường riêng (.venv)..."
  "$PY" -m venv .venv
fi

if [ ! -f .venv/.deps_ok ]; then
  echo "[2/3] Cài thư viện cơ bản..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/.deps_ok
fi

if [ ! -f .venv/.torch_ok ]; then
  echo "[3/3] Cài PyTorch cho tab So sánh Gemma (chỉ làm 1 lần)..."
  if .venv/bin/python setup_torch.py; then touch .venv/.torch_ok; else
    echo "[CẢNH BÁO] Chưa cài được PyTorch; tab So sánh Gemma tạm chưa dùng được."; fi
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo
  echo "Chưa thấy Ollama. Để trò chuyện với model lớn, hãy cài Ollama:"
  echo "  Linux: curl -fsSL https://ollama.com/install.sh | sh"
  echo "  macOS: tải tại https://ollama.com/download"
  echo
fi

exec .venv/bin/python app.py "$@"
