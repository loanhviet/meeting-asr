# Chạy và nghiệm thu

Trạng thái ngày 06/10/2026: [RELEASE_STATUS.md](RELEASE_STATUS.md). Các bước mới cho nhãn speech/ngữ cảnh ASR, cổng dữ liệu và nghiệm thu LLM/họp thật nằm trong [ACCEPTANCE.md](ACCEPTANCE.md); tài liệu này giữ các lệnh setup và kiểm tra luồng nền tảng.

## 1. Môi trường local

```bash
uv sync --locked --extra dev --extra inference --extra api
uv run --no-sync meeting-asr doctor
```

Tạo `.env` từ nội dung `.env.example`, điền token trên máy. `.env` được đọc tự động; biến môi trường đã có sẽ được ưu tiên. Không đưa khóa vào YAML, Git hoặc browser. Với RTX 3050 4 GB, bắt đầu bằng `MEETING_ASR_BATCH_SIZE=1`. Model chạy từng stage và được giải phóng trước stage tiếp; vẫn cần đo VRAM trên audio thật. CPU dùng `MEETING_DEVICE=cpu`. `asr.collect_no_speech` mặc định tắt để khỏi chạy thêm một lượt encoder. Chỉ bật trên một file pilot; nếu còn VRAM và tín hiệu đổi được lượt gắn cờ thì mới bật cho cả bộ.

Để dùng backend theo spec, đăng nhập và chấp nhận điều kiện của [speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) và [segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0). Token cần quyền đọc các model này. Download lần đầu cần mạng; không tự thay model khi quyền truy cập thất bại.

```bash
uv run --no-sync meeting-asr run data/real/meeting.wav --out results/local-demo
uv run --no-sync meeting-asr run data/real/meeting.wav --out results/local-ecapa --backend ecapa
uv run --no-sync meeting-asr benchmark data/real/meeting.wav --out results/benchmark
```

Kết quả mỗi lần chạy có RTTM, diarization signals, transcript thô, biên bản, trạng thái tóm tắt và manifest. Các file cache phụ thuộc audio, cấu hình upstream, seed, device, phiên bản thư viện và phiên bản implementation. Thay confidence không chạy lại ASR. `--no-cache` bỏ qua đọc cache và ghi kết quả mới. Benchmark mặc định bỏ qua cache, ghi RTF và **peak allocated VRAM**, không phải tổng bộ nhớ GPU toàn hệ thống; thêm `--cached` để đo luồng dùng cache.

## 2. Website

### Audio demo tổng hợp (không cần tự thu âm)

```bash
uv sync --locked --extra dev --extra inference --extra api --extra demo
uv run --no-sync meeting-asr demo-audio
```

Lệnh tạo `data/demo/demo_clean.wav`, `demo_noisy.mp3`, `demo_overlap.m4a`, các
bản WAV đi kèm và reference JSON/RTTM. Hai giọng nam/nữ tổng hợp đọc cùng nội
dung cuộc họp khoảng 90 giây; có bản rõ, nhiễu trắng 10 dB và chồng lấn.
Nội dung demo được gửi đến dịch vụ Microsoft Edge TTS để tạo giọng, không gửi
token Hugging Face hoặc audio người dùng. Lần đầu cần mạng; các clip được cache.
Script và nội dung được commit, audio sinh ra nằm trong `data/` bị Git bỏ qua.
Không dùng giọng tổng hợp hoặc mốc ghép clip để khẳng định DER/WER trên người thật.

Khi API bên dưới đang chạy, có thể kiểm tra ba định dạng upload với model thật:

```bash
uv run --no-sync python scripts/smoke_demo.py
```

Lệnh thêm ba job demo vào website, đánh dấu sửa thử ở turn đầu và đổi tên một
speaker thành “Người nói demo”. Kiểm tra lưu sửa, bản gốc bất biến, conflict
revision, nghe audio và export; kết quả nằm ở `results/demo-api-smoke/`.
LLM phải tắt khi chạy để không gọi provider bên ngoài.

Khi cả website và API đang chạy, kiểm tra trình duyệt với dữ liệu thật của các
job demo (không mock API):

```bash
node scripts/smoke_demo_web.mjs
```

Script kiểm tra playback cả ba định dạng, timeline, PDF download, tìm bản sửa
sau reload và layout mobile. Screenshot và báo cáo nằm cùng `results/demo-api-smoke/`.

Để thử toàn bộ công cụ đánh giá (chỉ smoke, không phải kết quả nghiên cứu):

```bash
uv run --no-sync meeting-asr experiments data/demo/sessions.json --out results/demo-experiments
uv run --no-sync meeting-asr evaluate-confidence results/demo-experiments/confidence_demo.json --out results/demo-confidence
```

Checkpoint Pyannote 3.x chứa metadata chưa có trong allowlist mặc định của
Torch 2.6+. Project dùng context allowlist cố định cho bốn kiểu metadata đã
biết, giữ weights-only loading; không tắt bảo vệ trên toàn process. Xem
[hướng dẫn serialization của PyTorch](https://docs.pytorch.org/docs/2.8/notes/serialization.html#torch-load-with-weights-only-true).

Từ thư mục gốc:

```bash
uv run --no-sync meeting-asr serve
```

Terminal khác:

```bash
cd web
npm ci
npm run dev
```

Mở `http://127.0.0.1:3000`. API mặc định `http://127.0.0.1:8000`; địa chỉ khác cấu hình bằng `web/.env.local` theo `web/.env.example`. Chạy đúng một process API/worker; lock từ chối worker thứ hai dùng cùng job store. Job và chỉnh sửa nằm trong `results/jobs/`. Khi process bị dừng, job đang chạy được xếp lại hàng đợi khi khởi động; stage đã cache được dùng lại.

Nghiệm thu website bằng **ba bản ghi họp tiếng Việt công khai**, có ít nhất một bản nhiều người nói và một đoạn nói chồng lấn. Nghe các đoạn bị gắn cờ. Không cần gán nhãn tay đủ RTTM cho cả ba bản:

1. Upload WAV/MP3/M4A, theo dõi trạng thái, đối chiếu nội dung với audio.
2. Click timestamp, nghe lại đoạn flagged và sửa text; bản gốc và lý do flag phải còn nguyên.
3. Đổi tên speaker, tải lại trang, kiểm tra tên/text và dấu đã soát được giữ.
4. Xuất Markdown/SRT/PDF; kiểm tra bản sửa và dấu tiếng Việt. Linux dùng DejaVu Sans có sẵn. Máy khác cần `MEETING_PDF_FONT` trỏ tới Unicode TTF hỗ trợ tiếng Việt.
5. Nếu bật LLM, sửa transcript phải làm tóm tắt cũ thành stale; bấm tạo lại. Export không sử dụng tóm tắt stale.

Website này là demo cá nhân chạy local, chưa có đăng nhập hoặc phân quyền. Chưa cấu hình triển khai cloud.

## 3. Tóm tắt

Mặc định tắt. Chọn provider/model rồi cấu hình `.env`:

```dotenv
MEETING_LLM_ENABLED=true
MEETING_LLM_PROVIDER=http
MEETING_LLM_MODEL=<model do bạn chọn>
MEETING_LLM_BASE_URL=<endpoint tương thích, kết thúc bằng /v1>
MEETING_LLM_API_KEY=<khóa trên máy>
```

Adapter `http` dùng Chat Completions và JSON mode theo [tài liệu Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). Với Claude, đặt provider `claude`; endpoint mặc định là API Messages. Dịch vụ local không cần key có thể đặt `llm.api_key_env: null` trong YAML. Khởi động lại API sau khi đổi cấu hình. Schema được kiểm tra, JSON lỗi được thử lại một lần, phản hồi thành công được cache; transcript dài được tóm tắt theo nhiều phần. Lỗi tóm tắt được ghi riêng và không làm mất transcript.

## 4. Dữ liệu và nghiên cứu

Dữ liệu không được commit vào repo. Cần chuẩn bị clip mono PCM16 16 kHz cùng manifest `{"clips": [...]}`. Mỗi clip có `clip_id`, `speaker` (ID người gốc), `text`, `source`, `license`, `wav`. Giữ nguồn/licensing của dữ liệu công khai. Các clip một người phải dùng cùng ID; speaker IDs không được chứa khoảng trắng.

```bash
uv run --no-sync meeting-asr prepare-data data/raw/clips.json --out data/audited --dev-speakers 3
uv run --no-sync meeting-asr build-dataset data/audited/test.json --out data/simulated/pilot --conversations 2
```

Nghe/vẽ waveform pilot trước khi sinh bộ chính. Manifest được kiểm tra trùng ID/checksum và chia theo speaker. Có thể truyền `prepare-data --exclude-hashes <file SHA256, mỗi dòng một hash>` để loại clip đã biết; bước này **không chứng minh dữ liệu sạch khỏi tập huấn luyện pretrained**. Không dùng VIVOS train; Common Voice cần kiểm tra trùng nguồn với PhoWhisper. Bộ sinh báo lỗi nếu clip không đủ hoặc mục tiêu overlap không khả thi, không tự hạ mục tiêu. Mặc định nhiễu trắng; dùng `--noise data/raw/musan_16k.wav` cho nhiễu thực.

Sau khi pilot đạt và xác nhận đủ clip, sinh test 20 hội thoại × 9 điều kiện. Dev là 30 file từ các hội thoại/speaker/clip riêng; `--conversations 4 --session-limit 30` hỗ trợ giới hạn số file. Kiểm tra phân bố điều kiện của 30 file dev trước khi cố định; đây không phải ma trận cân bằng đầy đủ. `--clips-per-speaker` điều chỉnh kích thước mỗi hội thoại. Không dùng các biến thể của cùng hội thoại như mẫu thống kê độc lập.

```bash
uv run --no-sync meeting-asr experiments data/simulated/pilot/sessions.json --out results/pilot
# Chạy experiments trên dev trước, tạo confidence_dev.json.
uv run --no-sync meeting-asr calibrate-confidence results/dev/confidence_dev.json --out results/dev-calibration.json --fit-weights
# Đóng băng kết quả rồi cấu hình đường dẫn trong .env:
# MEETING_CONFIDENCE_CALIBRATION=results/dev-calibration.json
uv run --no-sync meeting-asr evaluate-confidence results/test/confidence_test.json --out results/rq3
```

`experiments` xuất CSV RQ1/RQ2, dữ liệu từng file, precision/recall detector overlap, manifest dự đoán cho RQ3 và bootstrap theo hội thoại gốc. RQ2 bắt buộc `masking=none`; pipeline cũng từ chối mọi masking khác cho đến khi biến thể Input Masking được làm đúng. Giữ cả gap âm, relative gap bằng `null` khi mẫu số 0. DER relaxed không có speech sau khi bỏ overlap được ghi không xác định. Mỗi dòng cascaded và mỗi lần benchmark được nối thêm vào `results/experiments.csv`; miss, false alarm và confusion trong file đó là thành phần DER nới.

`calibrate-confidence` tính margin percentile trên dev; `--fit-weights` tìm trọng số theo mean F1 trên dev, threshold 0.30 và ngân sách 20%. File hiệu chỉnh được kiểm tra nhãn dev và hash khi nạp. Ngưỡng clustering ECAPA vẫn cần khảo sát trên dev bằng các YAML riêng; không chỉnh trên test.

RQ3 xuất JSON/CSV và PNG cho bốn biến thể, thresholds 0.20/0.30/0.50. Đường dùng **ngân sách thời lượng lượt nói** trên trục X và ghi thêm coverage thực tế. Turn nguyên vẹn có thể khiến ngân sách chưa dùng hết; coverage random/full có thể khác nhau dù cùng ngân sách. Mỗi từ tham chiếu thuộc nhiều nhất một turn, chia theo thời gian giao nhau. Nhãn `is_bad` so lời ASR của turn với đúng phần từ đó; turn không nhận từ nào là báo động giả. “Remaining WER” là tỷ lệ từ tham chiếu còn sai: turn được soát tính 0 lỗi, từ không turn nào phủ vẫn là lỗi, và soát thêm một turn không làm tỷ lệ tăng. Số này khác WER và cpWER cả file ở RQ1. Tỷ lệ thời lượng bỏ sót được báo riêng. Cần phân tích thêm sai speaker và nghe các đoạn chồng lấn.

AMI sanity check, oracle WER trên VIVOS test và bảng 9 điều kiện là cổng trước khi viết kết quả. Website cần 3 bản ghi họp công khai: nghe các đoạn bị gắn cờ, sửa, đổi tên, xuất file. Gán nhãn tay một cuộc khoảng 5 phút chỉ khi cần một số ngoài mô phỏng. So sánh Whisper turbo, Input Masking và benchmark T4 làm sau bảng chính, trên Colab nếu còn thời gian; thiếu thì ghi vào báo cáo. Notebook `notebooks/inference.ipynb` hỗ trợ chạy inference/benchmark trên Colab. Bộ phụ 60 phiên và EC2 không nằm trong phần bảo vệ.

## 5. Kiểm thử phần mềm

```bash
uv sync --locked --extra dev --extra api
uv run --no-sync pytest -q
uv run --no-sync ruff check src/meeting_asr tests
uv run --no-sync ruff format --check src/meeting_asr tests
uv build
```

Lệnh sync này phục vụ tests không cần model, có thể bỏ các gói inference đang cài; khi chạy model lại dùng sync đầy đủ ở mục 1. Không dùng `uv run` không có `--no-sync` sau khi cài extras vì nó có thể đồng bộ lại môi trường và bỏ extras không được yêu cầu.

```bash
cd web
npm ci
npx playwright install chromium
npm run format:check
npm run typecheck
npm run build
npm run test:e2e
```

Tests backend và browser dùng fixture/fake decoder cho các tình huống xác định, không thay thế nghiệm thu model thật. Browser test kiểm tra upload, sửa, tên speaker, summary stale, timeline, export và mobile. CI chạy các kiểm tra phần mềm, không tải model gated hay gọi LLM có phí.
