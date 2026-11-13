# Kế hoạch kiểm thử

Phạm vi lấy từ [TESTING.md](TESTING.md), [FEATURES.md](FEATURES.md),
[tests/](../tests/) và [web/tests/](../web/tests/).
Kết quả lần chạy này: [TEST_REPORT.md](TEST_REPORT.md).
Đối chiếu chức năng: [TRACEABILITY.md](TRACEABILITY.md).
Chất lượng model: [EVALUATION_REPORT.md](EVALUATION_REPORT.md).

## Phạm vi và cấp kiểm thử

| Cấp | Nội dung | Giới hạn |
|---|---|---|
| Unit | Audio, định dạng, cache, metrics, confidence, schema và patch | Fixture; không chứng minh accuracy model |
| Integration | Pipeline có fake decoder, FastAPI, SQLite, revision, export | Không chạy inference model thật |
| Browser | Upload → biên bản → nghe/sửa → hỏi đáp → export; mobile | Playwright dùng API fixture và audio có HTTP range |
| Nghiệm thu model | ASR/diarization trên dữ liệu có reference; review semantic | Tách khỏi test phần mềm; số đã công bố ở báo cáo đánh giá |

## Cách chạy

Từ gốc repo, cần Python theo [pyproject.toml](../pyproject.toml), `uv`,
FFmpeg/ffprobe để các test audio giải mã được WAV/MP3/M4A.

```bash
uv sync --locked --extra dev --extra api
uv run --no-sync pytest -q
```

Lệnh nhanh trên chạy toàn bộ `tests/` theo cấu hình pytest. Một số test tự skip
khi thiếu dependency tùy chọn; xem kết quả thực tế trong báo cáo chạy test.
Chạy riêng một nhóm: `uv run --no-sync pytest -q tests/test_api.py`.

Các kiểm tra phần mềm khác (lint, build, web; kết quả mới nhất trong [TEST_REPORT.md](TEST_REPORT.md)):

```bash
uv run --no-sync ruff check src/meeting_asr tests
uv run --no-sync ruff format --check src/meeting_asr tests
uv build
cd web
npm ci
npx playwright install chromium
npm run format:check
npm run typecheck
npm run build
npm run test:e2e
```

Playwright tự khởi động web bằng `npm run dev` theo
[playwright.config.ts](../web/playwright.config.ts).

## Các ca kiểm thử hiện có

Mỗi dòng là nhóm ca đã có trong file liên kết. Chạy file Python bằng mẫu lệnh
`uv run --no-sync pytest -q <file>`; chạy browser từ `web/` bằng
`npm run test:e2e -- tests/<file>.spec.ts`.

| ID | Nhóm chức năng | Kiểm tra | Test file / command |
|---|---|---|---|
| AU-01 | Tiền xử lý | Stereo, resample, normalization; decode MP3/M4A; chặn audio ngắn/im lặng | [test_preprocess.py](../tests/test_preprocess.py) |
| AU-02 | Định dạng | RTTM duration/overlap; JSON giữ Unicode và tín hiệu | [test_io.py](../tests/test_io.py) |
| AU-03 | Cache | Roundtrip, invalidation; metadata hỏng; trọng số stage sau không ảnh hưởng M1 | [test_cache.py](../tests/test_cache.py) |
| DA-01 | Dữ liệu | Chia speaker gốc, chặn clip trùng; clip riêng và ma trận dev giới hạn | [test_prepare.py](../tests/test_prepare.py), [test_dataset.py](../tests/test_dataset.py) |
| DA-02 | Mô phỏng | Overlap, SNR, clipping, seed, không lặp speaker liên tiếp; xuất reference | [test_simulate.py](../tests/test_simulate.py), [test_demo.py](../tests/test_demo.py) |
| DA-03 | Nhãn speech | Ranh giới, provenance người rà, hash audio; tách speech và oracle | [test_speech_labels.py](../tests/test_speech_labels.py) |
| DA-04 | Cổng dữ liệu | Thiếu nhãn/thời lượng; leakage; từ chối nhãn automatic ở cổng verified | [test_readiness.py](../tests/test_readiness.py) |
| AS-01 | DiCoW mặc định | Upload dispatch đúng engine; artifact; đường dẫn runtime và CLI | [test_default_engine.py](../tests/test_default_engine.py) |
| AS-02 | DiCoW bridge | Timestamp thật, overlap; từ chối text không timestamp/span sai; joint cache | [test_dicow.py](../tests/test_dicow.py) |
| AS-03 | ASR baseline | Chunk/reassembly, retry OOM, mảnh ngắn; không merge qua speaker khác | [test_asr.py](../tests/test_asr.py) |
| AS-04 | Diarization | Signal roundtrip; clustering/margin, overlap và clean anchors | [test_diarization.py](../tests/test_diarization.py), [test_ecapa.py](../tests/test_ecapa.py) |
| AS-05 | Pipeline/CLI | Resume sau lỗi, invalidation upstream, manifest và cổng số mẫu | [test_pipeline.py](../tests/test_pipeline.py), [test_cli.py](../tests/test_cli.py) |
| AS-06 | Checkpoint | Allowlist metadata; từ chối metadata lạ; khôi phục context | [test_checkpoints.py](../tests/test_checkpoints.py); cần Torch/Pyannote |
| CF-01 | Confidence | Thiếu tín hiệu, đơn điệu, budget, lý do tiếng Việt; flag decoding loop | [test_confidence.py](../tests/test_confidence.py) |
| CF-02 | Đánh giá confidence | Không đếm lặp reference; từ bỏ sót; calibration chỉ dùng dev | [test_confidence_evaluation.py](../tests/test_confidence_evaluation.py) |
| EV-01 | Metrics | NFC WER, hoán vị cpWER, strict/relaxed DER và overlap | [test_metrics.py](../tests/test_metrics.py) |
| EV-02 | Temporal metrics | Timing, speaker permutation, hypothesis rỗng, ORC và span sai | [test_paper_metrics.py](../tests/test_paper_metrics.py); scorer riêng |
| EV-03 | Thí nghiệm | Gap âm, bootstrap ghép cặp, log append; oracle khác speech reference | [test_experiments.py](../tests/test_experiments.py) |
| EV-04 | Đánh giá họp | Inference lỗi vẫn tính deletion; UEM, hash, duration; resume/rescore | [test_general_meeting_evaluation.py](../tests/test_general_meeting_evaluation.py) |
| EV-05 | Tuning | Chỉ dev, khóa checksum/budget; điều kiện chọn ứng viên | [test_asr_improvement.py](../tests/test_asr_improvement.py) |
| EV-06 | Benchmark | CPU không nhận VRAM GPU nhàn; DiCoW lấy số đo child process | [test_benchmark.py](../tests/test_benchmark.py) |
| LL-01 | Biên bản | JSON retry/cache; ID nguồn; timestamp/trạng thái soát; transcript dài | [test_summarize.py](../tests/test_summarize.py) |
| LL-02 | Gợi ý sửa | Unicode offset, patch nguy hiểm/mơ hồ/chồng; giữ nguồn, không gửi reference | [test_correction.py](../tests/test_correction.py) |
| LL-03 | LLM probe | Request giới hạn; không gửi transcript/khóa; phân loại lỗi | [test_llm_probe.py](../tests/test_llm_probe.py) |
| QA-01 | Hỏi đáp | Retrieval, nguồn, history/cache, revision, thiếu bằng chứng và lỗi provider | [test_ask.py](../tests/test_ask.py) |
| QA-02 | Nghiệm thu | Retrieval không tự thành semantic accuracy; review có provenance | [test_ask_evaluation.py](../tests/test_ask_evaluation.py), [test_acceptance.py](../tests/test_acceptance.py) |
| AP-01 | API | Upload, giới hạn dung lượng, conflict/retry, speaker, template, action và ETA | [test_api.py](../tests/test_api.py) |
| AP-02 | Persistence | Bản gốc bất biến, migration, recovery, history/merge; stale khi sửa đồng thời | [test_jobs.py](../tests/test_jobs.py) |
| EX-01 | Export | Bản sửa, stale summary, dẫn chứng; PDF font Unicode và escape markup | [test_export.py](../tests/test_export.py) |
| UI-01 | Luồng web | Upload/sửa/speaker, nguồn audio, review, loop, template/conflict và mobile | [meeting.spec.ts](../web/tests/meeting.spec.ts) |
| UI-02 | Hỏi đáp web | Nguồn/audio, history/stale; thiếu bằng chứng, LLM tắt, chống gửi lặp | [ask.spec.ts](../web/tests/ask.spec.ts) |

## Điều kiện đọc kết quả

- Test đạt chỉ chứng minh hành vi được assert trong fixture.
- Test skip phải được liệt kê; không tính là đã kiểm tra model/runtime thật.
- TODO: bổ sung test cho các khoảng trống trong TRACEABILITY.md và nghiệm thu
  semantic trên cuộc họp tiếng Việt có nhãn đã nghe rà.
