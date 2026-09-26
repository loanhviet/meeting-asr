# Meeting Minutes ASR

Hệ thống nghiên cứu biên bản họp tiếng Việt: diarization, ASR, đánh dấu lượt nói cần soát lại, tóm tắt và trích việc cần làm. Hiện repo đã triển khai **nền tảng, M1 tiền xử lý, bộ sinh hội thoại mô phỏng và thước đo DER/WER/cpWER**. Diarization, ASR, API và website nằm trong lộ trình tiếp theo.

## Cài đặt và chạy M1

Cần Python 3.11 hoặc 3.12, [uv](https://docs.astral.sh/uv/) và FFmpeg/ffprobe có `libsoxr`. Từ thư mục repo:

```bash
uv sync --extra dev
uv run meeting-asr preprocess /duong/dan/meeting.wav
uv run meeting-asr rttm-validate /duong/dan/meeting.rttm --file-id meeting_001
uv run pytest -q
uv run ruff check src/meeting_asr tests
```

`preprocess` nhận WAV/MP3/M4A, tạo mono float32 16 kHz, ghi cache vào `.cache/preprocess/` và manifest lần chạy vào `results/runs/`. Chạy lại cùng file/cấu hình sẽ dùng cache. Có thể truyền `--config configs/default.yaml` hoặc `--no-cache`. File dưới 5 giây, im lặng, hỏng hay có hơn 2 kênh được báo lỗi. File dài hơn 30 phút vẫn xử lý nhưng có cảnh báo.

## Sinh hội thoại mô phỏng

`simulate` đọc một manifest JSON các clip sạch mono 16-bit PCM 16 kHz và viết 9 file cho một hội thoại gốc: chồng lấn 0/15/30% kết hợp sạch / SNR 15 dB / SNR 5 dB. Cùng seed thì cùng thứ tự lượt nói; mỗi điều kiện chỉ đổi lịch chồng lấn và nhiễu. Nhiễu mặc định là nhiễu trắng cho đến khi có file MUSAN. Mỗi phiên ra `.wav`, `.rttm`, `.json` (lời tham chiếu, tín hiệu ASR để trống) và `.meta.json` (seed, nguồn clip, tỷ lệ chồng lấn thực tế).

```bash
uv run meeting-asr simulate data/raw/pilot_001.json --out data/simulated/pilot --index 1 --seed 42
```

```json
{
  "clips": [
    {"clip_id": "vivos_test_001", "speaker": "SPEAKER_00", "text": "xin chào", "source": "vivos-test", "wav": "001.wav"}
  ]
}
```

## Cấu trúc

- `src/meeting_asr/`: package Python và CLI; các stage sau sẽ thêm vào đây.
- `configs/`: tham số chạy. `configs/default.yaml` là cấu hình chuẩn.
- `tests/`: kiểm thử định dạng, M1, bộ sinh hội thoại và thước đo.
- `web/`: khung Next.js cho giai đoạn website.
- `data/`, `.cache/`, `results/`: dữ liệu và artifact local, phần lớn không theo dõi Git.
- `docs/`: bài báo, spec v2.1 và `PLAN.md` lưu **local**, không theo dõi Git theo lựa chọn của chủ repo. Cần backup riêng khi chuyển máy.

Đồ án dùng mô hình pretrained cho inference, không fine-tune trong phạm vi hiện tại. Colab Pro là môi trường chạy thí nghiệm; bản demo trước hết chạy local, EC2 GPU chỉ là phương án triển khai sau khi kiểm tra quota và chi phí.
