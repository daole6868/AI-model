# Tóm tắt & đánh giá: chuyển hành vi LFM3-1.7B sang Gemma-3-270M

> Đọc nhanh 4 nguồn trong bài chia sẻ "mổ não AI 1.7B", những gì đã được kiểm chứng bằng cách chạy thật, và những chỗ bài đăng nói quá.

## Kết luận ngắn

Thí nghiệm là **có thật và làm khá cẩn thận**, nhưng nhỏ hơn nhiều so với cách bài đăng mô tả: chỉ chuyển được **một** thói quen (chịu nghe lời dặn "Hãy trả lời bằng tiếng Việt"), tăng khoảng **+7 điểm** (62,7% → 69,7% trên 300 câu). Model không khôn hơn, chỉ đổi thói quen chọn ngôn ngữ.

## 1. Blog của Neeze: LFM3-1.7B → Gemma-3-270M

- **Thầy:** `LiquidAI/LFM3-1.7B` (24 tầng, 2048 chiều). **Trò:** `google/gemma-3-270m-it` (18 tầng, 640 chiều).
- **Bước 1 – ghép tầng:** cho hai model đọc cùng văn bản tiếng Việt, so độ giống nhau giữa các tầng. Cặp giống nhất: **tầng 21 của LFM3 ↔ tầng 16 của Gemma** (đều ở khoảng 85–90% chiều sâu). Dựng một phép biến đổi tuyến tính 2048 → 640 để "dịch" hướng hành vi.
- **Bước 2 – bẫy của Gemma 3:** Gemma 3 chuẩn hóa lại đầu ra MLP (`post_feedforward_layernorm`) trước khi cộng vào luồng chính. Phải cộng vector **sau** lớp chuẩn hóa này, nếu không hướng bị nắn lệch.
- **Bước 3 – kết quả:** một vector 640 số, khoảng 0,0002% tham số.

| Cấu hình | Trả lời tiếng Việt khi được dặn |
|---|---|
| Gemma gốc, dặn ở đầu câu | 52,3% |
| Gemma gốc, dặn ở cuối câu | 62,7% |
| **Gemma đã sửa, dặn ở cuối** | **69,7%** |

**Kiểm chứng của tác giả:** cộng vector thì tăng, trừ thì giảm (56% → 66% / 37%); vector ngẫu nhiên cùng độ lớn không làm được; Gemma Scope xếp vector này trùng khái niệm "đang nói tiếng Việt" (hạng 1/16.384).

**Tác giả tự nhận thất bại** ở: giọng lễ phép, độ trôi chảy, kiến thức tiếng Việt. Chỉ "nghe lời dặn tiếng Việt" là thành công.

## 2. Model trên Hugging Face (`Neeze/gemma-3-270m-it-vi-steer`)

Đã kiểm tra trực tiếp file weight:

- 640 con số **không sửa vào weight gốc**: chúng là một tensor riêng `steer_bias`. Mọi tensor khác **giống từng bit** với Gemma gốc.
- File `modeling_gemma3_vi.py` dùng `register_forward_hook` để cộng `steer_bias` vào đầu ra `post_feedforward_layernorm` của tầng 16 **lúc chạy** → cần `trust_remote_code=True`.
- AI Việt Studio tự gắn vector bằng hook tương đương; đã so sánh logits với code của tác giả: **sai lệch 0,0**.

Chạy thử 20 câu (tham lam, không ngẫu nhiên):

| Hệ số vector | Trả lời tiếng Việt |
|---|---|
| ×0 (gốc) | 13/20 = 65% |
| **×1 (bản mod)** | **17/20 = 85%** |
| ×−1 (đẩy ngược) | 9/20 = 45% |

Mẫu 20 câu là nhỏ, chỉ nên xem như xác nhận hướng tác động.

## 3. Weight-Space Programming (MIT CSAIL)

Đây là **khái niệm**, không phải công cụ: một LLM mạnh (GPT-6 Astra) tự suy luận để **đọc và ghi weight** của mạng nơ-ron, không dùng gradient. Ví dụ: đoán game từ weight thô; viết mạng chơi MinAtar thắng PPO 100 triệu bước; sửa 0,016% weight của Qwen3.5-0.8B để hết lặp suy luận (MATH-500 7,9% → 48,1%).

Kết luận trùng với bài của Neeze: với Gemma 3 270M, sửa weight **không** làm model giỏi toán hơn. *Sửa weight gỡ được chướng ngại, không thêm được năng lực.*

## 4. neuron-explorer

Công cụ khám phá neuron MLP cho **Qwen3.5-4B** (giấy phép MIT): bản đồ 3D, xếp hạng neuron, đẩy neuron lên/xuống để xem hành vi đổi ra sao. Phần quét cần GPU CUDA 13 thuê ngoài. Công cụ **không sửa hay xuất weight**.

## Những chỗ bài đăng Facebook nói quá

| Bài đăng nói | Thực tế |
|---|---|
| "Sửa chết trong file weight, không cần code lúc chạy" | Cần code tùy biến + hook. Chuyển sang GGUF (Ollama, LM Studio) là mất 640 số. |
| "Vá vào 640 neurons" | Là **một vector 640 chiều** cộng vào luồng chính, không sửa neuron nào. |
| "Trả lời tiếng Việt mượt, giống LFM3 hơn hẳn" | +7 điểm độ nghe lời. Phần "tự nhiên hơn" do chính LFM3 chấm (dễ thiên vị). |
| "Rút chuỗi hành vi" nói chung | Chỉ 1 trong 5 hành vi chuyển được. |

Thêm: biểu đồ đối chứng vector ngẫu nhiên có ghi chú "các chấm xám là minh họa"; blog không công bố code, bộ prompt hay hệ số scale nên khó tái lập.

## Nên dùng gì để có AI tiếng Việt thật sự?

Model 270M chỉ để thử nghiệm. Muốn trò chuyện tốt, hãy vào tab **Mô hình** và tải một model 4–8B (ví dụ `qwen3:8b`), chạy bằng Ollama trên GPU.
