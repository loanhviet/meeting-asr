# Meeting Minutes ASR

Hệ thống biên bản họp tiếng Việt: phân người nói, phiên âm, đánh dấu lượt nói cần soát, tóm tắt và trích việc cần làm. Có pipeline CLI, backend pyannote và ECAPA + overlap detector, PhoWhisper, confidence, bộ chạy RQ1–RQ3, FastAPI/SQLite và website Next.js để xem/sửa/export. **Code đã có; chất lượng model và kết quả nghiên cứu cần nghiệm thu trên dữ liệu thật.** Tỷ lệ từ còn sai của RQ3 không phải WER cả file. `asr.collect_no_speech` mặc định tắt.

Hướng dẫn setup token, chạy demo, chuẩn bị dữ liệu, thí nghiệm và checklist nghiệm thu: [TESTING.md](TESTING.md).

Trạng thái hiện tại và số đo đã kiểm tra: [RELEASE_STATUS.md](RELEASE_STATUS.md). Luồng nhãn speech, cổng dữ liệu, đánh giá LLM/họp thật và benchmark: [ACCEPTANCE.md](ACCEPTANCE.md). Có [sơ đồ kiến trúc](ARCHITECTURE.md) và [README tiếng Anh](README.en.md).

## Chạy bằng Docker

Cần Docker Engine và Docker Compose. Tạo `.env` từ `.env.example`, điền `HF_TOKEN` đã được cấp quyền cho các model Pyannote trước khi xử lý audio. Lần đầu build và tải model cần mạng, có thể tốn nhiều dung lượng và thời gian.

```bash
test -f .env || cp .env.example .env
mkdir -p data results .cache ~/.cache/huggingface
docker compose up --build -d
```

Mở `http://127.0.0.1:3000`. Website chuyển các yêu cầu `/api` tới FastAPI trong mạng Compose. Kiểm tra `http://127.0.0.1:3000/api/health`; xem log bằng `docker compose logs -f api web`. Dữ liệu trong `data/`, `results/` và `.cache/` được gắn từ thư mục dự án nên vẫn còn sau khi dừng container. Có thể chạy CLI trong container bằng `docker compose exec api meeting-asr doctor`.

Cache model Hugging Face trên máy (`~/.cache/huggingface`) cũng được dùng lại trong container; nếu cache của bạn nằm chỗ khác, đặt `HF_CACHE_PATH` thành đường dẫn đó trước khi chạy Compose. Lần build đầu Docker vẫn cần cài thư viện Python/Node riêng; các lần chạy lại dùng image và cache đã có.

API mặc định ghi file bằng UID/GID `1000:1000`; nếu tài khoản máy chủ dùng ID khác, đặt `DOCKER_UID=$(id -u) DOCKER_GID=$(id -g)` trước lệnh Compose.

Mặc định dùng target `cpu` với Torch/Torchaudio CPU, không cài các runtime CUDA. Nếu máy có NVIDIA GPU và NVIDIA Container Toolkit, chạy `docker compose -f compose.yaml -f compose.gpu.yaml up --build -d`; override chọn target `gpu`. Để `MEETING_DEVICE=auto` hoặc `cuda` trong `.env` khi dùng GPU; image CPU nên dùng `auto` hoặc `cpu`. Dừng bằng `docker compose down`. Image GPU và cache build có thể cần nhiều GB trên phân vùng Docker; kiểm tra dung lượng trước lần build đầu. Image web dùng Next standalone và chạy dưới user `node`.

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

## Hiệu chỉnh trên dev và kiểm tra lại pilot

Lần hiệu chỉnh ngày 02/10/2026 lưu bảng trước/sau, cấu hình và transcript mới trong `results/improvement-2026-10-02/`. Kết quả khuyến nghị ở `recommended/report.md`: ECAPA giảm WER 18,47% → 17,73%, cpWER 27,57% → 26,96% trên cùng 18 audio pilot. Chỉ có 2 hội thoại gốc, nên đây là kết quả thăm dò. Các thử nghiệm đổi clustering và calibration chưa tổng quát tốt cũng được giữ đầy đủ trong báo cáo riêng.

Chạy phương án cải thiện ASR bằng cấu hình `configs/improved-ecapa.yaml` (giữ clustering và trọng số confidence baseline; nối mảnh ASR tối đa 0,3 s đã chọn trên dev):

```bash
uv run --no-sync meeting-asr run /duong/dan/meeting.wav --config configs/improved-ecapa.yaml --out results/improved-demo
```

`diarization.ecapa.clean_clustering` cho phép tạo cụm từ cửa sổ đủ dài, không có chồng lấn do detector dự đoán, rồi gán các cửa sổ còn lại vào cụm. `asr.merge_same_speaker_gap` nối các mảnh gần nhau của cùng người nói trước khi phiên âm nếu không có người khác nói trong khoảng nghỉ; RTTM dự đoán gốc vẫn dùng để tính DER. Cả hai tùy chọn mặc định tắt để tái lập baseline.

Trong manifest thí nghiệm có thể đặt riêng `oracle_rttm` cho ngữ cảnh ASR. `reference_rttm` vẫn là nhãn speech dùng để chấm DER. Các nhãn speech tự động đề xuất phải được nghe kiểm tra trước khi dùng làm kết quả chính thức.
