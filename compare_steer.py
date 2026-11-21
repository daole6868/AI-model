"""So sánh Gemma-3-270M gốc và bản "steer" tiếng Việt (Neeze/gemma-3-270m-it-vi-steer).

Bản steer = Gemma gốc + đúng 1 vector 640 số (`steer_bias`) cộng vào sau
post_feedforward_layernorm của tầng 16. Mọi weight khác giữ nguyên, nên chỉ cần
tải MỘT model rồi đổi hệ số nhân của vector:
    0  -> đúng y Gemma gốc
    1  -> bản steer của tác giả
   -1  -> đẩy ngược (ít tiếng Việt hơn)
    2  -> đẩy gấp đôi (thử xem có "quá liều" không)

Cài đặt:
    pip install torch transformers        (Windows + GPU NVIDIA: lấy lệnh cài torch
                                           có CUDA ở https://pytorch.org/get-started/locally/)

Ví dụ:
    python compare_steer.py                        # 20 câu, so sánh hệ số 0 và 1
    python compare_steer.py --scales 0 1 -1 2      # thêm đẩy ngược và gấp đôi
    python compare_steer.py --prompt "What is the capital of France?"
    python compare_steer.py --chat                 # tự gõ câu hỏi, xem gốc vs steer
"""
import argparse
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.utils import logging as hf_logging

REPO = "Neeze/gemma-3-270m-it-vi-steer"
INSTRUCTION = "Hãy trả lời bằng tiếng Việt."  # đặt ở CUỐI câu hỏi (hiệu quả nhất theo blog)

PROMPTS = [
    "Describe the feeling of winning a big award.",
    "List three ways to conserve water.",
    "Explain why the sky is blue.",
    "Give me some tips for learning a new language.",
    "What are the benefits of regular exercise?",
    "Write a short story about a cat who loves the rain.",
    "How do I make a good cup of coffee?",
    "Explain what a computer virus is.",
    "What should I pack for a beach vacation?",
    "Describe your ideal weekend.",
    "Why is sleep important for health?",
    "Explain how plants make food from sunlight.",
    "Give three tips for saving money.",
    "What makes a good friend?",
    "Describe a busy city street in the morning.",
    "How can students manage stress during exams?",
    "Explain the difference between weather and climate.",
    "Write a short thank-you note to a teacher.",
    "What are some ways to reduce plastic waste?",
    "Describe the taste of your favorite fruit.",
]

VI_CHARS = set(
    "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
)


def is_vietnamese(text: str, threshold: float = 0.05) -> bool:
    """Đoán thô: tỉ lệ chữ cái có dấu tiếng Việt trên tổng số chữ cái."""
    letters = [c for c in text.lower() if c.isalpha()]
    if not letters:
        return False
    return sum(c in VI_CHARS for c in letters) / len(letters) >= threshold


def load(device: str):
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    tok = AutoTokenizer.from_pretrained(REPO)
    model = AutoModelForCausalLM.from_pretrained(REPO, trust_remote_code=True, dtype=dtype)
    model.to(device).eval()
    if not hasattr(model, "steer_bias"):
        sys.exit("Không thấy steer_bias: model chưa được tải qua code của tác giả (cần trust_remote_code=True).")
    original = model.steer_bias.detach().clone()
    return tok, model, original


@torch.no_grad()
def generate(tok, model, question: str, max_new_tokens: int) -> str:
    msgs = [{"role": "user", "content": question}]
    enc = tok.apply_chat_template(
        msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(model.device)
    out = model.generate(
        **enc, max_new_tokens=max_new_tokens, do_sample=False, top_k=None, top_p=None
    )
    return tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def set_scale(model, original, scale: float):
    model.steer_bias.data.copy_(original * scale)


def label(scale: float) -> str:
    return {0.0: "gốc (x0)", 1.0: "steer (x1)"}.get(scale, f"x{scale:g}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scales", type=float, nargs="+", default=[0.0, 1.0],
                    help="hệ số nhân vector steer (mặc định: 0 1)")
    ap.add_argument("--n", type=int, default=len(PROMPTS), help="số câu hỏi có sẵn sẽ chạy")
    ap.add_argument("--prompt", help="chạy một câu hỏi của bạn thay cho bộ có sẵn")
    ap.add_argument("--no-instruction", action="store_true",
                    help='không thêm "Hãy trả lời bằng tiếng Việt." vào cuối câu hỏi')
    ap.add_argument("--chat", action="store_true", help="chế độ tự gõ câu hỏi")
    ap.add_argument("--max-new-tokens", type=int, default=160)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    hf_logging.set_verbosity_error()

    print(f"Đang tải {REPO} lên {args.device} ...")
    tok, model, original = load(args.device)
    if args.device == "cuda":
        print("GPU:", torch.cuda.get_device_name(0))

    def ask(q: str) -> str:
        return q if args.no_instruction else f"{q}\n{INSTRUCTION}"

    if args.chat:
        print('Gõ câu hỏi (Enter trống để thoát). Lời dặn tiếng Việt được tự thêm vào cuối.')
        while True:
            try:
                q = input("\nBạn: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q:
                break
            for s in args.scales:
                set_scale(model, original, s)
                print(f"\n[{label(s)}] {generate(tok, model, ask(q), args.max_new_tokens)}")
        return

    questions = [args.prompt] if args.prompt else PROMPTS[: args.n]
    hits = {s: 0 for s in args.scales}
    t0 = time.time()
    for i, q in enumerate(questions, 1):
        print(f"\n{'=' * 70}\n[{i}/{len(questions)}] {ask(q)}")
        for s in args.scales:
            set_scale(model, original, s)
            ans = generate(tok, model, ask(q), args.max_new_tokens)
            vi = is_vietnamese(ans)
            hits[s] += vi
            short = ans.replace("\n", " ")
            print(f"\n  [{label(s)}] {'VI' if vi else 'EN'} | {short[:300]}{'...' if len(short) > 300 else ''}")

    print(f"\n{'=' * 70}\nTỉ lệ trả lời bằng tiếng Việt ({len(questions)} câu, {time.time() - t0:.0f}s):")
    for s in args.scales:
        print(f"  {label(s):12s} {hits[s]}/{len(questions)} = {100 * hits[s] / len(questions):.0f}%")
    print("(Đoán ngôn ngữ bằng tỉ lệ chữ có dấu, chỉ để tham khảo.)")


if __name__ == "__main__":
    main()
