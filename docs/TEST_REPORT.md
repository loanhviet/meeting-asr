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

## Phạm vi kết luận và phần còn thiếu

- Bộ Python hiện có đạt với các dependency trên; không chạy ASR/LLM thật.
- Chưa chạy Ruff, build, web typecheck/format/build, Playwright hoặc Docker
  trong lượt này; không lấy kết quả lịch sử làm kết quả mới.
- TODO: cài môi trường inference và scorer riêng để kiểm tra các ca đang skip.
- TODO: chạy các kiểm tra web và nghiệm thu model/semantic nếu cần xác nhận
  toàn hệ thống; xem TEST_PLAN.md và EVALUATION_REPORT.md.
