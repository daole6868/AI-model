# Đồ chơi "weight programming" chạy trên máy

Bộ cài cho các thứ trong bài chia sẻ về việc cấy hành vi từ LFM3-1.7B sang Gemma-3-270M:

| Thứ | Là gì | Chạy được trên |
|---|---|---|
| [Neeze/gemma-3-270m-it-vi-steer](https://huggingface.co/Neeze/gemma-3-270m-it-vi-steer) | Gemma-3-270M đã cộng thêm 640 con số sau `post_feedforward_layernorm` của tầng 16 | CPU thường, 0.5 GB |
| [neuron-explorer](https://github.com/lyramakesmusic/neuron-explorer) | Giao diện web soi từng neuron MLP của Qwen3.5-4B | CPU cho phần tra cứu; cần ~10 GB RAM/VRAM để chạy model trực tiếp |
| [RikiyaT/Qwen3.5-0.8B-weight-space-programming](https://huggingface.co/RikiyaT/Qwen3.5-0.8B-weight-space-programming) | Qwen3.5-0.8B đã sửa 0,016% weight để hết lặp vòng (thí nghiệm 8 của bài Weight-Space Programming) | CPU thường, 1.7 GB |

## Cài

Cần `git` và [`uv`](https://docs.astral.sh/uv/getting-started/installation/). Trên Linux/macOS (Windows thì dùng WSL):

```bash
./setup.sh            # Gemma đã mod + neuron-explorer (~12 GB đĩa, phần lớn là PyTorch)
./setup.sh --qwen     # thêm Qwen3.5-0.8B đã sửa weight
./setup.sh --qwen4b   # thêm Qwen3.5-4B (9.3 GB) cho neuron-explorer chạy model trực tiếp
```

## Chạy

**So sánh Gemma gốc và Gemma đã mod** (bản gốc = cùng model nhưng tắt vector 640 số):

```bash
.venv/bin/python scripts/chat_gemma_vi.py "Describe the feeling of winning a big award."
.venv/bin/python scripts/chat_gemma_vi.py     # hỏi đáp liên tục
```

Script tự thêm "Hãy trả lời bằng tiếng Việt." vào cuối câu hỏi. Model dùng `trust_remote_code=True`;
đoạn code đi kèm (`models/gemma-3-270m-it-vi-steer/modeling_gemma3_vi.py`) chỉ dài 18 dòng, đăng ký một hook cộng vector.

**Qwen3.5-0.8B đã sửa weight:**

```bash
.venv/bin/python scripts/chat_qwen_wsp.py "What is 17 * 23?"
```

**neuron-explorer:**

```bash
cd third_party/neuron-explorer
EXPLORER_NO_MODEL=1 uv run python explorer/server.py   # chỉ tra cứu từ cache, không nạp model
uv run python explorer/server.py                       # nạp Qwen3.5-4B (CUDA / MPS / CPU)
```

Mở http://localhost:8791. Lưu ý:

- Repo chỉ kèm cache lens/kết nối. Dữ liệu sweep (`runs/`, `stats/` — các rollout khi đẩy từng neuron) **không**
  có sẵn; muốn có phải tự chạy `sweep/` trên GPU CUDA với bản fork vLLM (xem README của neuron-explorer).
  Không có sweep thì tìm kiếm theo lens và xem lens/kết nối của neuron vẫn dùng được.
- Tab "Claude" cần cài và đăng nhập sẵn `claude` CLI.

## Về bài blog

- [Bài của Neeze](https://neeze.github.io/docs/practical-ai/weight-programming-lfm3-to-gemma/) không công bố code
  tìm/cấy vector, chỉ công bố model kết quả. Kết quả đo trong bài: tỉ lệ nghe lời dặn trả lời tiếng Việt tăng từ ~63% lên ~70%.
- [Weight-Space Programming](https://rikiyat.github.io/blog/weight-space-programming/) là một khái niệm, không phải
  công cụ để cài. Thứ chạy được là model Qwen ở trên; log đầy đủ ở
  [RikiyaT/lm_understand-logs](https://github.com/RikiyaT/lm_understand-logs).
