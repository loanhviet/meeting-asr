# Meeting Minutes ASR

Hệ thống hỗ trợ lập biên bản họp tiếng Việt: phân người nói, phiên âm, đánh dấu đoạn có độ tin cậy thấp, tóm tắt và trích xuất việc cần làm.

## Cấu trúc ban đầu

- `src/`: pipeline xử lý độc lập với web.
- `data_gen/`: sinh và kiểm tra dữ liệu mô phỏng.
- `evaluation/`: các metric và kịch bản đánh giá.
- `api/`: FastAPI backend.
- `web/`: Next.js frontend.
- `configs/`: cấu hình chạy pipeline.
- `tests/`: kiểm thử đơn vị.

Tài liệu đặc tả và bài báo tham chiếu nằm trong `docs/`.
