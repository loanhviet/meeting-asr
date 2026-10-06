# Trạng thái bàn giao — 06/10/2026

Code cho luồng xử lý, soát transcript, biên bản/hỏi đáp và công cụ nghiên cứu đã triển khai. Đã chạy model và LLM thật trên dữ liệu local; nghiệm thu nhãn speech, dữ liệu đủ thời lượng và cuộc họp người thật vẫn còn mở. Quy trình tiếp tục: [ACCEPTANCE.md](ACCEPTANCE.md).

## Phần đã hoàn tất trong repo

- ASR giữ thêm ngữ cảnh của các mảnh gần nhau cùng speaker; giữ RTTM dự đoán gốc để chấm DER. Profile ECAPA cải thiện là opt-in. Tuning và các thử nghiệm không tổng quát tốt được giữ riêng, có tham số đường dẫn để tái chạy.
- Hợp đồng `speech_intervals`/`speech_annotation` có checksum, phương pháp, phiên bản và trạng thái nghe kiểm chứng. WebRTC + năng lượng tạo đề xuất độc lập; trang offline cho nghe, sửa, xác nhận và export nhãn. Chỉnh nhãn đã xác nhận làm trạng thái trở lại cần soát.
- Bộ sinh phân biệt speech RTTM với utterance RTTM ngữ cảnh oracle; overlap và SNR dùng khoảng speech. Không thể đạt mục tiêu hoặc trộn loại nhãn thì báo lỗi. Không ghi đè dataset đã có manifest.
- Cổng số lượng/thời lượng clip, ma trận điều kiện, overlap, nhãn, provenance và trùng dữ liệu dev/test. Chế độ nghiêm ngặt chỉ dùng clip đã nghe; không tự nâng nhãn máy thành ground truth.
- Runner nghiệm thu LLM/họp thật, ba mẫu biên bản, hỏi đáp có nguồn, snapshot transcript đã sửa, review semantic có hash và coverage. Prompt hỏi đáp làm rõ thiếu dữ kiện; adapter có giới hạn output và lỗi timeout riêng. Báo cáo mới ghi model/prompt và hash endpoint, không in key.
- Benchmark nhiều file với thời lượng, RTF, từng stage và peak allocated VRAM theo device thực sự chạy.
- Docker CPU/GPU có target riêng; web standalone chạy không phải root và dùng proxy `/api`. CI có kiểm tra Compose CPU. README tiếng Anh, sơ đồ kiến trúc, manifest mẫu và hướng dẫn nghiệm thu đã có.

## Kiểm chứng phần mềm và vận hành

122 tests Python đạt; Ruff check/format, wheel/sdist và cài wheel trong một môi trường riêng đạt. Wheel có cấu hình default/improved và extra annotation. Website format/typecheck/production build và 11 Playwright tests đạt. Trang nghe nhãn cũng đã kiểm tra bằng Chromium với fixture riêng.

Docker CPU API/web đã build và chạy qua Compose với job store kiểm tra riêng: health, API proxy, trang production, preprocess, Torch CPU và WebRTC đều đạt. Không gọi model gated trong kiểm tra Compose. Target GPU chưa build/runtime nghiệm thu trong container; inference CUDA bên dưới chạy trên host. Lần build CUDA ban đầu cần quá nhiều dung lượng phân vùng Docker nên đã dừng, tách image CPU và giữ nguyên image/dữ liệu các project khác.

## Dữ liệu và số đo thực tế

VIVOS test local được chia thành dev 120 clip/3 speaker và test 640 clip/16 speaker. Đã tạo đề xuất nhãn cho toàn bộ 760 clip và trang nghe riêng. Chưa có clip nào trong các bản đề xuất này được người nghe xác nhận.

Đã sinh pilot speech mới 2 hội thoại × 9 điều kiện; kiểm tra ma trận, overlap speech và tách dev/test đạt. Đã chạy mới hai phiên sạch × oracle/Pyannote/ECAPA, tạo 4 dòng RQ1/RQ2 và chạy RQ3. Đây là kiểm tra pipeline với nhãn tự động, không phải số liệu nghiên cứu chính thức và không phải cùng cách nhóm hội thoại với pilot cũ.

Đã sinh **30 phiên dev và 180 phiên test dạng nháp**, với 20 hội thoại gốc trong test. Audit không thấy lỗi ma trận, overlap hay trùng clip/speaker/checksum dev/test. Tuy nhiên, toàn bộ test ngắn hơn 180 giây: khoảng **39–89 giây**, và nhãn chưa được nghe. Cổng nghiêm ngặt ghi đúng 360 vấn đề tương ứng hai điều kiện chưa đạt trên mỗi phiên. Pool test có khoảng **37,9 phút audio**, chưa đủ thiết kế thời lượng hiện tại nếu giữ clip riêng và giới hạn khoảng nghỉ của bộ sinh.

Benchmark ECAPA cải thiện, batch 1, không dùng cache pipeline, RTX 3050 Laptop:

| Audio pilot mới | Thời lượng | Xử lý | RTF | Peak CUDA allocated |
| --- | ---: | ---: | ---: | ---: |
| Hội thoại sạch 1 | 73,48 s | 22,86 s | 0,311 | 1,72 GiB |
| Hội thoại sạch 2 | 66,55 s | 17,78 s | 0,267 | 1,72 GiB |

Đây là hai lượt trên audio ngắn, không đại diện benchmark 5/15/30 phút hay tổng VRAM hệ thống. LLM tắt trong các phép đo ASR/diarization/benchmark.

## LLM thật

Đã chạy provider HTTP/model `qwen3.7-max` do cấu hình local chọn. Không ghi key vào repo. Trên transcript chuẩn tổng hợp hiện có:

| Phép kiểm tra | Đúng trạng thái | Từ chối đúng câu thiếu bằng chứng | Retrieval đủ nguồn chuẩn |
| --- | ---: | ---: | ---: |
| Prompt cũ, 14 câu | 10/14 | 2/6 | 8/8 |
| Prompt sửa, cùng 14 câu | 12/14 | 4/6 | 8/8 |
| Hội thoại độc lập, 6 câu | 4/6 | 1/3 | 3/3 |

Prompt đã được sửa sau khi xem lỗi trên bộ 14 câu; cải thiện trên bộ này là thăm dò. Bộ độc lập cho thấy khả năng từ chối còn hạn chế. Các tỷ lệ trên chấm **status/ID nguồn**, không phải độ đúng về nghĩa.

Đã chạy audio tổng hợp rõ/nhiễu/chồng lấn qua ASR rồi provider thật: **WAV, MP3, M4A đều hoàn tất; 9/9 biên bản của ba mẫu có JSON và ID nguồn hợp lệ**. Review semantic cho 9 biên bản vẫn để trống. Giọng tổng hợp không thay thế ba cuộc họp người thật. Dịch vụ Edge TTS không tạo được audio mới cho bộ độc lập trong lần thử này; bộ đó chỉ đánh giá text và ghi timestamp placeholder.

## Artifact local và việc còn lại

Các đường dẫn dưới đây là artifact local, không bundled trong Git:

- [Trang nghe pilot 36 clip](results/completion/speech-review/index.html), [dev 120 clip](results/completion/dev-speech-review/index.html), [test 640 clip](results/completion/test-speech-review/index.html).
- [Audit pilot mới](results/completion/pilot-speech-audit.json), [cổng bộ test nháp](results/completion/main-study-readiness.json).
- [RQ1/RQ2 smoke](results/completion/model-smoke/inference/rows.json), [RQ3](results/completion/model-smoke/rq3/rq3.json), [benchmark](results/completion/benchmark/suite.json).
- [LLM trước sửa](results/completion/llm-gold/evaluation/report.json), [sau sửa](results/completion/llm-gold/evaluation-ask2/report.json), [bộ độc lập](results/completion/holdout/evaluation-configured.json).
- [End-to-end ASR/LLM](results/completion/end-to-end/evaluation/report.json), [mẫu review semantic](results/completion/end-to-end/evaluation/review-template.json), [browser Compose](results/completion/docker-browser.json).

Trước khi chốt đồ án: nghe xác nhận nhãn; bổ sung nguồn clip đủ thời lượng có speaker/text/provenance và kiểm tra trùng nguồn pretrained; hiệu chỉnh trên dev rồi cố định cấu hình/chạy bộ test chính; hoàn tất AMI sanity check và oracle WER VIVOS; nghiệm thu ba bản họp người thật; chấm semantic và đo audio 5/15/30 phút. Báo cáo kết quả không đạt phải giữ và phân tích. Whisper turbo, Input Masking, T4 và cloud là các mục sau bảng chính theo phạm vi hiện tại.

Backup `docs/`, nhãn/manifest và artifact cần trích trước khi chuyển máy. Credentials, audio và model cache giữ local. Chuẩn bị video demo 2–3 phút theo luồng trong [ACCEPTANCE.md](ACCEPTANCE.md).
