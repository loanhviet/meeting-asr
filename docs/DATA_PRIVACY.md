# Dữ liệu và quyền riêng tư

Tài liệu này mô tả luồng được thể hiện trong code/cấu hình hiện tại. Xem thêm [Hướng dẫn người dùng](USER_MANUAL.md) và [Kế hoạch dự án](PROJECT_PLAN.md).

## Dữ liệu và nơi lưu

| Dữ liệu | Xử lý / lưu trữ theo code |
|---|---|
| Audio WAV/MP3/M4A | API nhận file tối đa 200 MiB, ghi vào `results/jobs/{job_id}/audio.*`; API phát lại file này. Pipeline có thể tạo cache và artifact kết quả. |
| Transcript, timestamp, speaker ID, cờ soát | Kết quả pipeline/artifact; bản sửa text, trạng thái đã soát, gán speaker, tên speaker và lịch sử sửa lưu qua `jobs.sqlite3`. |
| Biên bản, việc, người tham dự, tiêu đề, trạng thái job | Thông tin job và kết quả trong SQLite/artifact. Người tham dự được nhập qua API. |
| Câu trả lời Hỏi cuộc họp | Lịch sử payload và revision lưu trong bảng `ask_answers`; có thư mục `ask-cache`. |
| Model và cache | `.cache/`, cache Hugging Face/torch; Compose gắn `data/`, `results/`, `.cache/` và Hugging Face cache từ host vào API. |

Không thấy trong code giao diện API xóa job hay chính sách tự hết hạn dữ liệu. **TODO: thời hạn lưu, quy trình xóa audio/job/cache và backup cần chủ dự án xác định.**

## Dịch vụ ngoài

- Khi LLM được bật, cấu hình dùng HTTP endpoint tương thích OpenAI, model mặc định `gemini-3-flash`; API key đọc từ `MEETING_LLM_API_KEY`. Nếu chọn `llm.provider: claude` mà không đặt `base_url`, code dùng `https://api.anthropic.com/v1` (`src/meeting_asr/summarize.py`). Tóm tắt và Hỏi cuộc họp gửi transcript/nội dung liên quan tới endpoint cấu hình. Nhà cung cấp thực tế phụ thuộc URL cấu hình.
- Runtime tải model/checkpoint qua Hugging Face khi chưa có cache; cấu hình yêu cầu `HF_TOKEN` để đọc checkpoint tương ứng. Audio inference trong pipeline không đồng nghĩa gửi audio tới LLM: code tách xử lý model ASR và yêu cầu LLM.
- **TODO: xác minh endpoint/provider thực tế, điều khoản lưu/xử lý của nhà cung cấp và việc có telemetry ở môi trường triển khai hay không.**

## Rủi ro và giảm thiểu

| Rủi ro | Biện pháp hiện có / cần làm |
|---|---|
| Audio và transcript chứa thông tin cá nhân | Compose bind dữ liệu vào thư mục local; giới hạn demo local. TODO: quy định quyền truy cập, thời hạn lưu và xóa. |
| Nội dung gửi tới LLM bên ngoài khi bật | LLM tắt mặc định; chỉ bật khi cấu hình endpoint/key. Xác định provider và kiểm tra điều khoản trước khi xử lý dữ liệu thật. |
| SQLite và cache để lại bản sửa/nội dung | Lưu local trong job store/artifact/cache. TODO: thủ tục dọn/xóa đồng bộ các bản. |
| Website/API demo chưa có ownership/xác thực nhiều người dùng | Tài liệu kiến trúc ghi nhận triển khai nhiều người dùng cần bổ sung ownership, xác thực và điều phối worker. Không đưa endpoint công khai trước khi giải quyết. |
| Transcript/biên bản có thể sai hoặc suy diễn | Giao diện đánh dấu lượt cần soát, cho nghe nguồn; kiểm tra ID nguồn không chứng minh nội dung đúng nghĩa. Người dùng cần kiểm tra trước khi chia sẻ. |
