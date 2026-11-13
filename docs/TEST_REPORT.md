# Báo cáo chạy kiểm thử

Liên quan: [kế hoạch](TEST_PLAN.md), [truy vết](TRACEABILITY.md),
[chất lượng model](EVALUATION_REPORT.md).

## Lần chạy thực tế

| Mục | Kết quả |
|---|---|
| Ngày | 13/11/2026, múi giờ Asia/Bangkok |
| Thư mục chạy | Gốc repo `meeting_asr/redfish` |
| Môi trường | Python 3.12.3; pytest 9.1.1; venv `.venv` mới |
| Chuẩn bị | `uv sync --locked --extra dev --extra api` — thành công |
| Lệnh test | `uv run --no-sync pytest -q` |
| Số lượt chạy | Một lượt |
| Exit code | 0 |
| Passed | 177 |
| Failed | 0 |
| Skipped | 6 |
| Warning | 1 |
| Thời gian pytest | 8,12 giây |

Đầu ra tổng kết nguyên văn:

```text
177 passed, 6 skipped, 1 warning in 8.12s
```

## Skip và warning

Đối chiếu điều kiện skip trong test và dependency của môi trường vừa cài:

| File | Số skip | Nguyên nhân |
|---|---:|---|
| [test_checkpoints.py](../tests/test_checkpoints.py) | 3 | `pytest.importorskip("torch")`; môi trường dev/api không cài Torch. Test còn yêu cầu `pyannote.audio`. |
| [test_paper_metrics.py](../tests/test_paper_metrics.py) | 3 | Chưa có `.cache/paper-eval/venv/bin/python`; skip các ca gọi scorer. Các ca kiểm timestamp không cần scorer vẫn chạy. |

Warning: `StarletteDeprecationWarning` từ `fastapi/testclient.py`: dùng `httpx`
với `starlette.testclient` đã deprecated; thông báo đề nghị cài `httpx2`.
Không có test failure hoặc collection error trong lượt này.

## Kiểm tra bổ sung (cùng ngày)

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| Lint Python | `uv run --no-sync ruff check src/meeting_asr tests` | Đạt |
| Format Python | `uv run --no-sync ruff format --check src/meeting_asr tests` | Đạt, 79 file |
| Web typecheck | `npm run typecheck` (trong `web/`) | Đạt |
| Web format | `npm run format:check` | Đạt |
| Web build | `npm run build` | Đạt |
| Web e2e | `npm run test:e2e` (Playwright, Chromium) | 12 passed |

`ruff check .` toàn repo báo 7 lỗi I001 trong notebook `notebooks/*.ipynb`; lỗi này có sẵn,
không thuộc phạm vi lệnh CI ở trên.

## Phạm vi kết luận và phần còn thiếu

- Các bộ test hiện có đạt với dependency trên; không chạy ASR/LLM thật.
- Chưa chạy `uv build` và Docker trong lượt này; không lấy kết quả lịch sử làm kết quả mới.
- TODO: cài môi trường inference và scorer riêng để kiểm tra 6 ca đang skip.
- TODO: nghiệm thu model/semantic và inference CUDA trong container nếu cần xác nhận
  toàn hệ thống; xem TEST_PLAN.md và EVALUATION_REPORT.md.
