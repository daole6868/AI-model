"""Chạy Qwen3.5-0.8B đã được sửa weight (thí nghiệm 8 trong bài Weight-Space Programming).

    .venv/bin/python scripts/chat_qwen_wsp.py "What is 17 * 23?"

Cần chạy ./setup.sh --qwen trước để tải model.
"""
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

REPO = os.path.join(os.path.dirname(__file__), "..", "models", "Qwen3.5-0.8B-weight-space-programming")
if not os.path.isdir(REPO):
    REPO = "RikiyaT/Qwen3.5-0.8B-weight-space-programming"

tok = AutoTokenizer.from_pretrained(REPO)
model = AutoModelForCausalLM.from_pretrained(REPO, dtype=torch.float32).eval()

question = " ".join(sys.argv[1:]) or "What is 17 * 23? Show your work briefly."
msgs = [{"role": "user", "content": question}]
enc = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)
with torch.no_grad():  # thông số sampling theo bài blog
    out = model.generate(**enc, max_new_tokens=int(os.environ.get("MAX_NEW_TOKENS", 1024)),
                         do_sample=True, temperature=0.6, top_p=0.95, top_k=20)
print(tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True).strip())
