# Hướng dẫn sử dụng AI Việt Studio

AI Việt Studio là ứng dụng chạy **ngay trên máy bạn**: câu hỏi không bị gửi lên Internet. Ứng dụng có 5 tab:

| Tab | Dùng để |
|---|---|
| **Trò chuyện** | Chat với AI như ChatGPT, lưu lịch sử, chọn model |
| **So sánh Gemma** | So sánh Gemma-3-270M gốc và bản "nghe lời tiếng Việt" cạnh nhau |
| **Mô hình** | Tải, xem và xóa các model AI |
| **Tài liệu** | Tải bộ bài viết gốc về máy để đọc offline, xuất cả bộ thành .zip |
| **Cài đặt** | Lời nhắc hệ thống, độ sáng tạo, cỡ chữ, giao diện sáng/tối |

## 1. Cài đặt lần đầu

1. Cài **Python 3.10 trở lên** tại python.org. Khi cài, **tick ô "Add python.exe to PATH"**.
2. Nên cập nhật driver NVIDIA mới nhất (nếu có card NVIDIA).
3. Giải nén file zip, nhấp đúp **`CHAY_WINDOWS.bat`**.
4. Lần đầu, chương trình sẽ:
   - cài thư viện (khoảng 3 GB, 5–15 phút);
   - hỏi bạn có muốn **cài Ollama** không: chọn **Y** (đồng ý). Ollama là phần mềm miễn phí giúp chạy các model lớn trên GPU.
5. Trình duyệt tự mở `http://127.0.0.1:7860`. Giữ cửa sổ đen mở trong lúc dùng.

## 2. Tải model để trò chuyện

1. Vào tab **Mô hình**. Ô trạng thái phải báo **Ollama đang chạy**.
   - Nếu chưa: mở ứng dụng Ollama (biểu tượng con lạc đà ở khay hệ thống) hoặc bấm **Tải Ollama** rồi cài.
2. Ở mục **Gợi ý cho máy của bạn**, bấm **Tải về** ở model muốn dùng:
   - `qwen3:8b` (khoảng 5,2 GB): khuyên dùng cho card 8 GB, tiếng Việt tốt, biết "suy nghĩ" trước khi trả lời.
   - `qwen3:4b` (khoảng 2,5 GB): nhẹ, nhanh.
3. Chờ thanh tiến độ chạy xong (tốc độ tùy mạng). Model tải một lần, dùng mãi.
4. Muốn model khác: gõ tên ở mục **Tải model khác** (xem danh sách tại ollama.com/library).

## 3. Trò chuyện

- Chọn model ở góc trên, gõ câu hỏi rồi nhấn **Enter** (Shift+Enter để xuống dòng).
- Câu trả lời hiện dần; bấm **Dừng** để ngắt.
- Với model biết suy nghĩ (như Qwen3), bấm **Xem suy nghĩ** để xem quá trình lập luận.
- Dưới mỗi câu trả lời: **Sao chép**, **Tạo lại**, số token và tốc độ.
- Lịch sử lưu ở cột bên trái (trong thư mục `data/` của ứng dụng). Có ô tìm kiếm, nút xóa, và nút **Tải .md** để lưu cuộc trò chuyện.

## 4. So sánh Gemma

Hỏi một lần, xem Gemma gốc và bản tiếng Việt trả lời cạnh nhau. Thanh **Độ mạnh vector**: 0 = gốc, 1 = bản của tác giả, số âm = đẩy ngược. Lần đầu dùng sẽ tải model khoảng 540 MB.

## 5. Tài liệu

Bấm **Tải tất cả về máy** để tải các bài viết gốc (kèm hình). Sau đó đọc offline ngay trong ứng dụng, hoặc bấm **Tải cả bộ (.zip)** để lưu ra máy.

## 6. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| "Khong tim thay Python" | Cài Python, tick "Add python.exe to PATH", chạy lại |
| Cài thư viện lỗi giữa chừng | Xóa thư mục `.venv` rồi chạy lại `CHAY_WINDOWS.bat` |
| Tab Mô hình báo Ollama chưa chạy | Mở ứng dụng Ollama, rồi bấm **Kiểm tra lại** |
| Trả lời rất chậm | Chọn model nhỏ hơn (4B) hoặc giảm "Độ dài ngữ cảnh" trong Cài đặt |
| Cổng 7860 bận | Ứng dụng tự chuyển sang 7861, 7862… xem địa chỉ trong cửa sổ đen |

## 7. Lưu ý

AI có thể sai. Hãy kiểm tra lại thông tin quan trọng. Các model tải về tuân theo giấy phép riêng của từng nhà phát triển (Qwen, Gemma, Llama…).
