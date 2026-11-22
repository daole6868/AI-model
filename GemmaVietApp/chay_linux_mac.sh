#!/usr/bin/env bash
# Gemma Việt - chạy trên Linux / macOS:  bash chay_linux_mac.sh
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  PY=$(command -v python3 || command -v python || true)
  if [ -z "$PY" ]; then
    echo "[LỖI] Không tìm thấy Python 3.10+. Hãy cài Python rồi chạy lại."; exit 1
  fi
  echo "[1/2] Tạo môi trường riêng (.venv)..."
  "$PY" -m venv .venv
fi

if [ ! -f .venv/.da_cai_xong ]; then
  echo "[2/2] Cài thư viện (lần đầu mất vài phút)..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python setup_torch.py
  touch .venv/.da_cai_xong
fi

exec .venv/bin/python app.py "$@"
