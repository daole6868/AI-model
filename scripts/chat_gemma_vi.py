"""So sánh Gemma-3-270M gốc và bản đã cấy 640 con số (Neeze/gemma-3-270m-it-vi-steer).

    .venv/bin/python scripts/chat_gemma_vi.py "Describe the feeling of winning a big award."
    .venv/bin/python scripts/chat_gemma_vi.py            # hỏi đáp liên tục

Bản "gốc" ở đây chính là model đã mod với vector 640 số bị tắt (đặt về 0), nên không
cần tải thêm google/gemma-3-270m-it.
"""
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

REPO = os.path.join(os.path.dirname(__file__), "..", "models", "gemma-3-270m-it-vi-steer")
if not os.path.isdir(REPO):
    REPO = "Neeze/gemma-3-270m-it-vi-steer"
SUFFIX = "\nHãy trả lời bằng tiếng Việt."  # đặt lời dặn ở CUỐI câu hỏi thì hiệu quả hơn

tok = AutoTokenizer.from_pretrained(REPO)
model = AutoModelForCausalLM.from_pretrained(REPO, trust_remote_code=True).eval()
steer = model.steer_bias.data.clone()
print(f"Đã nạp model. Vector cấy: {steer.numel()} số, độ lớn {steer.float().norm():.2f}\n")


def answer(question, steered):
    model.steer_bias.data.copy_(steer if steered else torch.zeros_like(steer))
    msgs = [{"role": "user", "content": question + SUFFIX}]
    enc = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=128, do_sample=False)
    return tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def compare(question):
    print(f"Hỏi: {question}{SUFFIX}")
    print(f"\n[Gemma gốc]\n{answer(question, False)}")
    print(f"\n[Gemma đã mod]\n{answer(question, True)}\n" + "-" * 60)


if len(sys.argv) > 1:
    compare(" ".join(sys.argv[1:]))
else:
    while True:
        try:
            q = input("Câu hỏi (Enter để thoát): ").strip()
        except EOFError:
            break
        if not q:
            break
        compare(q)
