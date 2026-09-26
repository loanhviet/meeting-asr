# Kết quả kiểm tra local — 2026-09-26

## Đã xác nhận

- Quyền đọc cả `pyannote/speaker-diarization-3.1` và `pyannote/segmentation-3.0`.
- Pyannote khởi tạo và inference trên CUDA sau bản sửa metadata allowlist; ECAPA/OSD chạy được.
- 59 tests Python qua. Môi trường CI nhẹ không có inference: 56 qua, 3 bỏ qua.
- Ruff và build Python qua; website format/typecheck/build và 2 tests Playwright qua.
- Sinh hai giọng tiếng Việt tổng hợp, 10 lượt, ba điều kiện rõ/nhiễu/chồng lấn.
- Chạy 3 điều kiện × (oracle, Pyannote, ECAPA); xuất 6 dòng so sánh và 18 biểu đồ confidence.
- API thật nhận WAV/MP3/M4A; lưu sửa/đổi tên, giữ bản gốc, chặn revision cũ và xuất MD/SRT/PDF.
- Trình duyệt thật phát cả ba định dạng, mở timeline, tải PDF, tìm bản sửa sau reload; mobile không tràn ngang.

## Các audio để thử

| File local | Thời lượng | Điều kiện |
| --- | ---: | --- |
| `data/demo/demo_clean.wav` | 91,6 giây | Hai giọng luân phiên, rõ |
| `data/demo/demo_noisy.mp3` | 91,6 giây | Cùng nội dung, nhiễu trắng 10 dB |
| `data/demo/demo_overlap.m4a` | 83,6 giây | Cùng nội dung, năm đoạn nói chồng lấn |

Có thêm WAV và reference JSON/RTTM trong `data/demo/`. Audio/output sinh ra
không nằm trong Git; dùng `meeting-asr demo-audio` để tạo lại. Các job demo
lưu trong `results/jobs/`, cùng job của người dùng; smoke script không xóa job.
Turn đầu được sửa thử với hậu tố `[đã kiểm tra demo]` và một speaker được đặt
tên “Người nói demo” để xác nhận persistence. Bản model gốc vẫn giữ nguyên.

## Benchmark và hạn chế

RTX 3050 Laptop GPU, Torch 2.8, PhoWhisper-medium, ASR batch size 1:
bản rõ 91,6 giây xử lý không cache khoảng 30,6 giây (RTF 0,334), peak CUDA
allocated 1,73 GiB. Đây không phải tổng VRAM hệ thống hay benchmark T4.

Pyannote nhận hai speaker ở cả ba demo. ECAPA mặc định nhận 3/4/4 speaker
tương ứng rõ/nhiễu/chồng lấn; cần hiệu chỉnh clustering trên **dev người thật**,
không ép số speaker hay dùng demo này để chọn tham số nghiên cứu.

LLM vẫn tắt vì chưa có provider/model/key được chọn. Chưa gọi LLM thật;
adapter, schema, retry và stale-summary đã kiểm tra bằng tests mô phỏng.
Chưa có corpus người thật để xác nhận chỉ tiêu DER/WER, calibration nghiên cứu
hoặc triển khai cloud. Website là demo cá nhân local, chưa có authentication.

Hướng dẫn chạy và nghiệm thu tiếp: [TESTING.md](TESTING.md).
