# Triển khai Docker Compose

Nguồn: [README.md](../README.md), [compose.yaml](../compose.yaml),
[compose.gpu.yaml](../compose.gpu.yaml), [Dockerfile](../Dockerfile),
[web/Dockerfile](../web/Dockerfile), [.env.example](../.env.example).
Xem [kiến trúc](SAD.md) và [dữ liệu/API](DATABASE_API.md).

## Chuẩn bị

- Cần Docker Engine và Docker Compose hỗ trợ `env_file.required`, GPU `gpus` khi dùng GPU.
- Chạy lệnh từ thư mục gốc repo; lần đầu cần mạng để build dependency và tải model.
- Điền `HF_TOKEN` có quyền đọc checkpoint DiCoW, DiariZen và WeSpeaker.
- Image cài runtime tác giả đã pin ở `/opt/dicow`; weights tải/cache khi inference đầu tiên.
- Cấu hình mặc định là `configs/default.yaml`: DiariZen + DiCoW, LLM tắt.

```bash
test -f .env || cp .env.example .env
mkdir -p data results .cache ~/.cache/huggingface
```

Chỉnh `.env` trên máy trước khi khởi động. Nếu cache Hugging Face nằm chỗ khác,
đặt `HF_CACHE_PATH` trước lệnh Compose; không ghi credential vào tài liệu/YAML.

## CPU

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f api web
```

Compose chọn build target `cpu` với Torch/Torchaudio CPU. Trong `.env`,
`MEETING_DEVICE` dùng `auto` hoặc `cpu`; CPU phù hợp kiểm tra chức năng.

## NVIDIA GPU

Cần NVIDIA GPU, driver và NVIDIA Container Toolkit. Trong `.env`,
`MEETING_DEVICE` dùng `auto` hoặc `cuda`; nên dùng GPU cho audio họp.

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
docker compose -f compose.yaml -f compose.gpu.yaml ps
```

Override chọn target `gpu`, runtime Torch CUDA `cu128` và `gpus: all`.
TODO: xác minh inference CUDA trong container trên máy triển khai;
[ARCHITECTURE.md](ARCHITECTURE.md) chỉ ghi nhận smoke Docker CPU và GPU host.

## Biến môi trường và cấu hình

Chỉ liệt kê tên biến; giá trị điền trên máy theo `.env.example`.

| Nhóm | Tên | Khi cần |
| --- | --- | --- |
| Quyền tải model | `HF_TOKEN` | Trước inference cần checkpoint có kiểm soát quyền |
| Thiết bị | `MEETING_DEVICE`, `MEETING_ASR_BATCH_SIZE` | Chọn thiết bị/batch; DiCoW decode từng target |
| LLM | `MEETING_LLM_ENABLED`, `MEETING_LLM_PROVIDER`, `MEETING_LLM_MODEL`, `MEETING_LLM_BASE_URL`, `MEETING_LLM_API_KEY`, `MEETING_LLM_ENABLE_THINKING` | Khi bật tóm tắt/hỏi đáp |
| Confidence/PDF | `MEETING_CONFIDENCE_CALIBRATION`, `MEETING_PDF_FONT` | Tùy chọn; image đã có DejaVu Sans cho PDF |
| Compose trên host | `WEB_HOST`, `WEB_PORT`, `DOCKER_UID`, `DOCKER_GID`, `HF_CACHE_PATH` | Đổi địa chỉ/cổng, quyền ghi, vị trí cache |
| Runtime do image/Compose đặt | `MEETING_DICOW_PYTHON`, `MEETING_DICOW_UPSTREAM_DIR`, `MEETING_DICOW_RUNTIME_MANIFEST` | Trỏ runtime `/opt/dicow`, không dùng venv cache host |
| Cache do Compose đặt | `HOME`, `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME` | Giữ cache trong volume |
| Web do Compose đặt | `MEETING_API_INTERNAL_URL`, `NEXT_PUBLIC_API_URL` | Proxy tới API nội bộ; browser dùng cùng origin |

Các phần YAML: `runtime`, `preprocess`, `diarization`, `asr`, `dicow`,
`postprocess`, `confidence`, `llm`, `paths`, `evaluation`, `seed`.
Dockerfile gọi `serve --config /app/configs/default.yaml`; nếu sửa YAML đóng gói,
build lại image. Đổi `.env` cần tạo lại container bằng `docker compose up -d`.

## Cổng và dữ liệu bền vững

| Thành phần | Địa chỉ/cổng mặc định | Ghi chú |
| --- | --- | --- |
| Web trên host | `http://127.0.0.1:3000` | Đổi bằng `WEB_HOST`, `WEB_PORT` |
| API trong mạng Compose | `http://api:8000` | Không publish cổng 8000 ra host |
| API qua web | `http://127.0.0.1:3000/api/...` | Next.js proxy các đường dẫn `/api` |
| Bind mounts | `data/`, `results/`, `.cache/`, cache Hugging Face | Giữ sau khi dừng container; jobs ở `results/jobs/` |

## Kiểm tra và dừng

```bash
curl -f http://127.0.0.1:3000/api/health
docker compose exec api meeting-asr doctor
docker compose down
```

- Health cần `status=ok`, `asr_engine=dicow`, `diarization_backend=diarizen`.
- Health xác nhận cấu hình server; doctor kiểm tra runtime không tải model,
  cần `dicow_runtime.ready=true`. Hai bước này chưa chứng minh model inference thành công.
- Compose probe API mỗi 10 giây, timeout 6 giây, retries 6, start period 30 giây;
  web chỉ khởi động sau khi API healthy.
- Dùng cùng `-f compose.yaml -f compose.gpu.yaml` cho lệnh quản lý stack GPU.
- Chỉ chạy một API/worker cho cùng job store; restart xếp lại job running, dùng stage cache.

## Lỗi thường gặp

| Hiện tượng | Kiểm tra/cách xử lý |
| --- | --- |
| Tải model bị từ chối | Kiểm tra `HF_TOKEN`, quyền đọc từng checkpoint và mạng; không tự đổi model |
| CPU image báo CUDA không khả dụng | Đặt `MEETING_DEVICE` thành `auto`/`cpu`, hoặc dùng GPU override đúng môi trường |
| GPU container không thấy GPU | Kiểm tra driver, NVIDIA Container Toolkit và GPU override; đọc log `api` |
| `Permission denied` khi ghi volume | API mặc định UID/GID 1000:1000; dùng lệnh bên dưới theo ID tài khoản host |
| Web chưa lên hoặc proxy lỗi | Kiểm tra `docker compose ps`, health và log `api web` |
| Build/tải lần đầu lâu hoặc hết đĩa | Kiểm tra mạng, phân vùng Docker và cache; GPU image/build cache cần nhiều dung lượng |
| Upload thất bại | Chỉ WAV/MP3/M4A, tối đa 200 MiB; pipeline từ chối audio dưới 5 giây, im lặng, hỏng hoặc hơn 2 kênh |
| Không có biên bản/hỏi đáp | LLM mặc định tắt; kiểm tra biến LLM, endpoint/key/quota, tạo lại container và đọc `summary_error` |
| Job cũ không đổi engine | Kết quả cũ được giữ; upload thành job mới để nhận dạng bằng cấu hình mới |
| FileLock từ chối worker | Dừng process API thứ hai đang dùng cùng `results/jobs/` |

```bash
DOCKER_UID=$(id -u) DOCKER_GID=$(id -g) docker compose up --build -d
```
