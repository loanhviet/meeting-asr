# Thiết kế hệ thống

Tài liệu kiến trúc và thiết kế của Meeting Minutes ASR. Các sơ đồ lập theo snapshot
30/10/2026 và đối chiếu với mã nguồn lúc đó; sơ đồ 09 và 17 chưa cập nhật theo giao diện
mới (PR #4). Schema và API **hiện tại**: [DATABASE_API.md](../DATABASE_API.md). Giới hạn hệ thống:
[ARCHITECTURE.md](../ARCHITECTURE.md). Cách chạy: [DEPLOYMENT.md](../DEPLOYMENT.md).

## Kiến trúc đã triển khai

Next.js phục vụ giao diện React; FastAPI nhận file, quản lý job và trả bản đã sửa. `JobWorker`
là một thread trong backend, xử lý tuần tự với file lock theo store root. SQLite WAL giữ metadata,
bản sửa và câu trả lời; audio/JSON/RTTM lưu trên filesystem.

Luồng mặc định là **DiariZen → STNO/FDDT → DiCoW**, chạy trong subprocess với Python runtime riêng.
Pyannote/ECAPA → PhoWhisper chỉ chọn bằng cấu hình baseline tường minh. M1–M5 chuẩn bị bản chữ và
cờ soát; M6 tóm tắt tùy cấu hình. Hỏi đáp dùng BM25 và gọi LLM trực tiếp trong request API, không
qua `JobWorker`. Chưa có auth/ownership hay ASR streaming.

## Sơ đồ

Mỗi sơ đồ có nguồn Mermaid/PlantUML trong `diagrams/`, bản SVG và liên kết tới mã nguồn.

| Sơ đồ | Hình |
|---|---|
| [01 — Use Case Diagram](views/01-use-case-diagram.md) | `diagrams/svg/01-use-case-diagram.svg` |
| [02 — Meeting Processing Activity Diagram](views/02-activity-meeting-processing.md) | `diagrams/svg/02-activity-meeting-processing.svg` |
| [03 — System Context Diagram](views/03-system-context-diagram.md) | `diagrams/svg/03-system-context-diagram.svg` |
| [04 — Container Diagram](views/04-container-diagram.md) | `diagrams/svg/04-container-diagram.svg` |
| [05 — Backend Component Diagram](views/05-component-backend.md) | `diagrams/svg/05-component-backend.svg` |
| [06 — Meeting Processing Data Flow Diagram](views/06-data-flow-diagram.md) | `diagrams/svg/06-data-flow-diagram.svg` |
| [07 — Meeting Processing Sequence Diagram](views/07-sequence-meeting-processing.md) | `diagrams/svg/07-sequence-meeting-processing.svg` |
| [08 — AI Summarization Sequence Diagram](views/08-sequence-ai-summarization.md) | `diagrams/svg/08-sequence-ai-summarization.svg` |
| [09 — Meeting Questions Sequence Diagram](views/09-sequence-meeting-questions.md) | `diagrams/svg/09-sequence-meeting-questions.svg` |
| [10 — Entity Relationship Diagram](views/10-entity-relationship-diagram.md) | `diagrams/svg/10-entity-relationship-diagram.svg` |
| [11 — AI Processing Pipeline](views/11-ai-processing-pipeline.md) | `diagrams/svg/11-ai-processing-pipeline.svg` |
| [12 — Deployment Diagram](views/12-deployment-diagram.md) | `diagrams/svg/12-deployment-diagram.svg` |
| [13 — Domain Model Class Diagram](views/13-class-domain-model.md) | `diagrams/svg/13-class-domain-model.svg` |
| [14 — Job Lifecycle State Machine](views/14-state-job-lifecycle.md) | `diagrams/svg/14-state-job-lifecycle.svg` |
| [15 — Transcript Review Sequence Diagram](views/15-sequence-transcript-review.md) | `diagrams/svg/15-sequence-transcript-review.svg` |
| [16 — DiCoW Inference Sequence Diagram](views/16-sequence-dicow-inference.md) | `diagrams/svg/16-sequence-dicow-inference.svg` |
| [17 — Frontend Component Diagram](views/17-component-frontend.md) | `diagrams/svg/17-component-frontend.svg` |

## Tech stack

| Thành phần | Công nghệ trong repo |
| --- | --- |
| App/CLI | Python 3.11–3.12, `uv`, YAML; image dùng Python 3.12 |
| API và lưu trữ | FastAPI, Uvicorn, Pydantic, SQLite/WAL, FileLock |
| Web | Next.js 16.3.6, React 19.3.0, TypeScript, Tailwind CSS 4 |
| Audio | FFmpeg/ffprobe, NumPy, SciPy, pyloudnorm |
| Inference chính | PyTorch/Torchaudio, runtime DiCoW tác giả được pin riêng |
| Model mặc định | `BUT-FIT/DiCoW_v3_MLC`, `BUT-FIT/diarizen-wavlm-large-s80-md`, WeSpeaker embedding |
| LLM | Adapter HTTP tương thích OpenAI hoặc Claude; mặc định model `gemini-3-flash`, LLM tắt |
| Export | Markdown, SRT; ReportLab và Unicode TTF cho PDF |
| Kiểm thử/triển khai | pytest, Ruff, Playwright; Docker Compose CPU/GPU, Next standalone |

## Quyết định thiết kế

| Quyết định | Lý do/ngữ cảnh |
| --- | --- |
| DiariZen + DiCoW là luồng chính | Theo hướng nghiên cứu transcript theo người nói và overlap đã chốt, xem [README](../../README.md) và [ARCHITECTURE.md](../ARCHITECTURE.md). |
| Dùng checkpoint MLC pretrained | Có checkpoint đa ngôn ngữ; tích hợp inference, chưa fine-tune hoặc tái lập toàn benchmark paper. |
| Giữ Pyannote/ECAPA + PhoWhisper | Là baseline đối chứng tường minh, không phải cấu hình mặc định. |
| Tách runtime tác giả | Giữ dependency/pin riêng khỏi môi trường app; xem [DICOW.md](../DICOW.md). |
| Giải phóng diarizer, decode tuần tự | Giảm nhu cầu VRAM giữa hai model. |
| Cache theo stage và provenance | Dùng lại stage phù hợp khi chạy lại, tránh tái dùng kết quả khi upstream đổi. |
| SQLite và một worker | Phù hợp demo local; worker xếp lại job đang chạy sau restart. |
| Artifact gốc + bản sửa theo revision | Giữ output model, phát hiện sửa đồng thời, nhận biết đầu ra LLM stale. |
| Dẫn chứng bằng turn ID | Backend đối chiếu nguồn thật thay vì nhận timestamp do LLM tự tạo. |

Confidence DiCoW thiếu token log probability và cluster margin, để `null`, chưa calibration.
TODO: nghiệm thu chất lượng và công nghe sửa trên bộ họp tiếng Việt có nhãn đã soát;
xem [kế hoạch đánh giá](https://github.com/loanhviet/meeting-asr/blob/0b641e4/document/GENERAL_MEETING_PLAN_2026-10-26.md).
