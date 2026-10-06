# Nghiệm thu dữ liệu, model và biên bản

Trạng thái và bằng chứng gần nhất: [RELEASE_STATUS.md](RELEASE_STATUS.md). Các lệnh dưới đây chạy từ thư mục repo; luôn dùng thư mục output mới cho mỗi phiên bản dữ liệu. `build-dataset` từ chối ghi đè một bộ đã có `sessions.json`.

## 1. Nhãn tiếng nói và ngữ cảnh ASR

Manifest clip giữ nguyên `wav`, `text`, người nói, nguồn, license và checksum. Nhãn bổ sung dùng thời gian **tương đối trong clip**, không phải thời gian của cuộc họp:

```json
{
  "speech_intervals": [[0.12, 1.8], [2.1, 3.42]],
  "speech_annotation": {
    "status": "automatic_unverified",
    "method": "webrtc-energy-conservative",
    "version": "v1"
  }
}
```

Nhãn được kiểm tra phải có `status: human_verified`, `reviewed_by` và `reviewed_at`. Công cụ không tự nâng nhãn máy thành nhãn đã nghe. Khoảng phải hữu hạn, tăng dần, không chồng nhau và nằm trong clip. File audio đổi checksum thì phải tạo/soát lại nhãn.

```bash
uv sync --locked --extra dev --extra api --extra inference --extra demo --extra annotation
uv run --no-sync meeting-asr propose-speech data/audited/dev.json --out data/audited/dev-proposed.json
uv run --no-sync meeting-asr review-speech data/audited/dev-proposed.json --out results/dev-review
python -m http.server 8080 --bind 127.0.0.1 --directory results/dev-review
```

Mở `http://127.0.0.1:8080`, nghe clip, sửa các khoảng và xác nhận bằng tên người soát. Trang lưu tiến độ trong trình duyệt; tải `speech-labels.reviewed.json` để giữ bản bền vững. Import file tải về bằng checksum, không dùng đường dẫn audio trong file tải về:

```bash
uv run --no-sync meeting-asr import-speech data/audited/dev.json /duong/dan/speech-labels.reviewed.json --out data/audited/dev-reviewed.json
uv run --no-sync meeting-asr build-dataset data/audited/dev-reviewed.json --out data/simulated/dev-v2 --conversations 4 --session-limit 30 --require-verified-speech
```

Lặp lại với pool test. Khi bật `--require-verified-speech`, bộ sinh chỉ chọn clip đã được người nghe xác nhận; số clip bị loại được ghi trong manifest. Thiếu clip/người nói hoặc không thể đạt mục tiêu overlap thì lệnh báo lỗi.

WebRTC VAD và ngưỡng năng lượng chỉ đề xuất bỏ khoảng yên lặng dài, giữ ngữ cảnh 100 ms; có thể bỏ sót lời nhỏ hoặc giữ nhiễu. Đây là nhãn tự động độc lập với diarizer đang chấm, **không phải ground truth thủ công**. Nhãn đề xuất cũ có `proposed_intervals` cũng import được.

Mỗi phiên mới có:

- `.rttm`: khoảng **speech**, phục vụ DER và overlap.
- `.oracle.rttm`: khoảng **utterance**, giữ ngữ cảnh ASR oracle.
- `.json`: lời tham chiếu theo utterance, phục vụ WER/cpWER/RQ3.
- `.meta.json`: clip gốc, checksum, nhãn/phương pháp và tỷ lệ overlap của speech lẫn utterance.

Overlap 0/15/30% và SNR sạch/15/5 dB được tính trên khoảng speech khi có nhãn. Không có nhãn thì công cụ giữ hành vi cũ và ghi `full_clip_unverified`. Không trộn hai loại tham chiếu trong một hội thoại.

## 2. Cổng dữ liệu và RQ1–RQ3

```bash
uv run --no-sync meeting-asr plan-data data/audited/test-reviewed.json --conversations 20 --clips-per-speaker 6 --minimum-duration-sec 180 --out results/test-capacity.json
uv run --no-sync meeting-asr audit-experiments data/simulated/test-v2/sessions.json --other-manifest data/simulated/dev-v2/sessions.json --expected-conversations 20 --minimum-duration-sec 180 --require-verified-speech --out results/test-readiness.json
```

Các cổng ghi JSON và trả exit code 2 khi chưa đạt. `plan-data` kiểm tra số clip/người nói và giới hạn tổng thời lượng; đây chưa phải bảo đảm lịch overlap khả thi. `audit-experiments` kiểm tra đủ 9 điều kiện, cùng nội dung/thứ tự lượt, overlap, thời lượng, clipping, nhãn và trùng clip/speaker/checksum giữa dev/test.

Chỉ hiệu chỉnh trên dev. Cố định YAML và file calibration trước khi chạy test. Mỗi lần chạy giữ cấu hình và artifact riêng; `configs/improved-ecapa.yaml` là phương án cải thiện ngữ cảnh ASR thăm dò, chưa thay thế mọi baseline.

```bash
MEETING_LLM_ENABLED=false uv run --no-sync meeting-asr experiments data/simulated/dev-v2/sessions.json --out results/dev-v2 --require-verified-speech
uv run --no-sync meeting-asr calibrate-confidence results/dev-v2/confidence_dev.json --out results/dev-v2/calibration.json --fit-weights
# Cấu hình calibration/clustering đã chọn trên dev trong YAML/.env trước bước test.
MEETING_LLM_ENABLED=false uv run --no-sync meeting-asr experiments data/simulated/test-v2/sessions.json --out results/test-v2 --require-verified-speech --expected-conversations 20 --other-manifest data/simulated/dev-v2/sessions.json
uv run --no-sync meeting-asr evaluate-confidence results/test-v2/confidence_test.json --out results/test-v2/rq3
```

20 hội thoại gốc là đơn vị thống kê; 180 biến thể không độc lập. RQ2 giữ `masking=none`. RQ3 phải báo cáo cả bốn biến thể và phần lời bỏ sót; tỷ lệ từ còn sai sau soát khác WER cả file. Kết quả full kém baseline vẫn phải giữ và phân tích.

## 3. LLM thật và bản ghi họp thật

```bash
uv run --no-sync meeting-asr llm-check
```

Lệnh chỉ kiểm tra cấu hình, không gửi request hoặc in key. Provider/model/endpoint/key lấy từ cấu hình đã chọn trong `.env`. `llm.max_output_tokens` mặc định 1800; timeout được báo thành lỗi riêng. Chỉ `--provider configured` mới gửi nội dung tới provider.

Tạo manifest riêng theo [examples/meeting-acceptance.json](examples/meeting-acceptance.json), thay đường dẫn, nguồn và điều kiện sử dụng. Mỗi câu có đáp án cần `answer` và `source_turn_ids` có thật trong transcript; câu thiếu bằng chứng dùng `status: not_found`, `answer: null`, nguồn rỗng.

```bash
uv run --no-sync meeting-asr evaluate-meetings data/real/acceptance.json --out results/real-retrieval
uv run --no-sync meeting-asr evaluate-meetings data/real/acceptance.json --provider configured --out results/real-llm
```

`minutes` nhận `minutes.json` hoặc snapshot JSON của `GET /api/jobs/{id}/result`. Snapshot dùng bản **edited**, gồm trạng thái đã soát; LLM không nhận bản text bị thay thế. Để xử lý audio mới, dùng `--run-asr`; tạo nguồn chuẩn theo turn ID của transcript mới trước khi chấm hỏi đáp. Một manifest không có câu hỏi vẫn chạy đánh giá ba mẫu biên bản. Nếu có reference JSON/RTTM, chế độ ASR có thể chấm WER/cpWER/DER.

`report.json` lưu câu hỏi, nguồn, đầu ra biên bản, lỗi và provenance. `review-template.json` để trống ba tiêu chí `correct`, `complete`, `supported`. Người chấm điền boolean, tên, thời điểm ISO và ghi chú, rồi chạy:

```bash
uv run --no-sync meeting-asr score-review results/real-llm/report.json results/real-llm/reviewed.json --out results/real-llm/semantic-scores.json
```

Bộ chấm từ chối review trùng hoặc không khớp hash câu trả lời. Luôn báo coverage; các mục chưa chấm không được coi là đúng. Kiểm tra trạng thái/ID nguồn không đo độ đúng về nghĩa. Kiểm thử giọng tổng hợp không thay thế ba cuộc họp người thật.

Nghiệm thu website trên ba bản ghi khác nhau: upload, nghe lượt flagged, sửa lời/người nói, reload, tạo lại biên bản, hỏi đáp, xuất Markdown/SRT/PDF và đối chiếu bản sửa. Ghi lỗi quyết định/owner/deadline riêng với lỗi câu chữ nhỏ.

## 4. Hiệu năng và bàn giao

```bash
MEETING_LLM_ENABLED=false uv run --no-sync meeting-asr benchmark-suite data/real/meeting_5min.wav data/real/meeting_15min.wav data/real/meeting_30min.wav --config configs/improved-ecapa.yaml --out results/benchmark-real
```

`suite.json`/`suite.csv` ghi thời lượng, RTF, từng stage, phiên bản, device và peak allocated VRAM. Mặc định bỏ qua cache; `--cached` cho phép cache và ghi rõ chế độ. Chạy CPU không đọc VRAM của GPU nhàn rỗi. Đo một lượt có thể gồm chi phí khởi tạo model; không suy ra p95 hay khả năng chịu nhiều người dùng từ một lượt.

Hướng dẫn Docker: [README.md](README.md). CPU là image mặc định, GPU dùng target riêng. CI kiểm tra phần mềm và Compose CPU, không tải model gated hoặc gọi LLM có phí. Khi bàn giao, backup `docs/`, manifest/nhãn và artifact cần trích trong báo cáo; audio, model cache và `.env` nằm ngoài Git. Chuẩn bị video 2–3 phút: upload → sửa lượt khó → xem nguồn biên bản → hỏi đáp → export.
