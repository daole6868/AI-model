# AI-model

## AI Việt Studio

Ứng dụng AI chạy ngay trên máy tính, giao diện tiếng Việt, gồm 5 tab:

| Tab | Chức năng |
|---|---|
| **Trò chuyện** | Chat với AI như ChatGPT (qua [Ollama](https://ollama.com)), lưu lịch sử, xem phần "suy nghĩ" |
| **So sánh Gemma** | So sánh Gemma-3-270M gốc và bản "nghe lời tiếng Việt" (`Neeze/gemma-3-270m-it-vi-steer`) |
| **Mô hình** | Tải / xóa model, có thanh tiến độ và gợi ý model hợp với card 8 GB |
| **Tài liệu** | Tải bộ bài viết gốc (kèm hình) về máy, đọc offline, xuất thành .zip |
| **Cài đặt** | Lời nhắc hệ thống, độ sáng tạo, ngữ cảnh, cỡ chữ, sáng/tối |

**Tải về:** file [`AIVietStudio.zip`](AIVietStudio.zip). Giải nén, rồi nhấp đúp `CHAY_WINDOWS.bat`. Xem chi tiết trong `AIVietStudio/HUONG_DAN.txt`.

Yêu cầu: Windows 10/11 (hoặc Linux/macOS), Python 3.10+. Nên có card NVIDIA (ví dụ RTX 4060 8 GB).

## Công cụ dòng lệnh

`compare_steer.py`: so sánh nhanh Gemma gốc và bản steer trên 20 câu hỏi, in tỉ lệ trả lời bằng tiếng Việt.

```bash
pip install torch transformers
python compare_steer.py --scales 0 1 -1
```
