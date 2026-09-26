# Meeting Minutes ASR

Hệ thống biên bản họp tiếng Việt: phân người nói, phiên âm, đánh dấu lượt nói cần soát, tóm tắt và trích việc cần làm. Có pipeline CLI, backend pyannote và ECAPA + overlap detector, PhoWhisper, confidence, bộ chạy RQ1–RQ3, FastAPI/SQLite và website Next.js để xem/sửa/export. **Code đã có; chất lượng model và kết quả nghiên cứu cần nghiệm thu trên dữ liệu thật.**

Hướng dẫn setup token, chạy demo, chuẩn bị dữ liệu, thí nghiệm và checklist nghiệm thu: [TESTING.md](TESTING.md).

```bash
uv sync --locked --extra dev --extra inference --extra api
uv run --no-sync meeting-asr doctor
uv run --no-sync meeting-asr run data/real/meeting.wav --out results/demo
uv run --no-sync meeting-asr serve
# Terminal khác: cd web && npm ci && npm run dev
```

## Cài đặt và chạy M1

Cần Python 3.11 hoặc 3.12, [uv](https://docs.astral.sh/uv/) và FFmpeg/ffprobe có `libsoxr`. Từ thư mục repo:

```bash
uv sync --locked --extra dev --extra api
uv run --no-sync meeting-asr preprocess /duong/dan/meeting.wav
uv run --no-sync meeting-asr rttm-validate /duong/dan/meeting.rttm --file-id meeting_001
uv run --no-sync pytest -q
uv run --no-sync ruff check src/meeting_asr tests
```

`preprocess` nhận WAV/MP3/M4A, tạo mono float32 16 kHz, ghi cache vào `.cache/preprocess/` và manifest lần chạy vào `results/runs/`. Chạy lại cùng file/cấu hình sẽ dùng cache. Có thể truyền `--config configs/default.yaml` hoặc `--no-cache`. File dưới 5 giây, im lặng, hỏng hay có hơn 2 kênh được báo lỗi. File dài hơn 30 phút vẫn xử lý nhưng có cảnh báo.

## Sinh hội thoại mô phỏng

`simulate` đọc một manifest JSON các clip sạch mono 16-bit PCM 16 kHz và viết 9 file cho một hội thoại gốc: chồng lấn 0/15/30% kết hợp sạch / SNR 15 dB / SNR 5 dB. Cùng seed thì cùng thứ tự lượt nói; mỗi điều kiện chỉ đổi lịch chồng lấn và nhiễu. Nhiễu mặc định là nhiễu trắng cho đến khi có file MUSAN. Mỗi phiên ra `.wav`, `.rttm`, `.json` (lời tham chiếu, tín hiệu ASR để trống) và `.meta.json` (seed, nguồn clip, tỷ lệ chồng lấn thực tế).

```bash
uv run --no-sync meeting-asr simulate data/raw/pilot_001.json --out data/simulated/pilot --index 1 --seed 42
```

```json
{
  "clips": [
    {"clip_id": "vivos_test_001", "speaker": "SPEAKER_00", "text": "xin chào", "source": "vivos-test", "wav": "001.wav"},
    {"clip_id": "vivos_test_002", "speaker": "SPEAKER_01", "text": "chào các bạn", "source": "vivos-test", "wav": "002.wav"},
    {"clip_id": "vivos_test_003", "speaker": "SPEAKER_02", "text": "bắt đầu cuộc họp", "source": "vivos-test", "wav": "003.wav"}
  ]
}
```

## Cấu trúc

- `src/meeting_asr/`: pipeline, backend model, confidence, API và công cụ nghiên cứu.
- `configs/`: tham số chạy. `configs/default.yaml` là cấu hình chuẩn.
- `tests/`: kiểm thử định dạng, M1, bộ sinh hội thoại và thước đo.
- `web/`: website Next.js, TypeScript/Tailwind và kiểm thử Playwright.
- `data/`, `.cache/`, `results/`: dữ liệu và artifact local, phần lớn không theo dõi Git.
- `docs/`: bài báo, spec v2.1 và `PLAN.md` lưu **local**, không theo dõi Git theo lựa chọn của chủ repo. Cần backup riêng khi chuyển máy.

Đồ án dùng mô hình pretrained cho inference, không fine-tune trong phạm vi hiện tại. Colab Pro là môi trường chạy thí nghiệm; bản demo trước hết chạy local, EC2 GPU chỉ là phương án triển khai sau khi kiểm tra quota và chi phí.
