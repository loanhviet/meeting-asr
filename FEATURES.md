# Biên bản có dẫn chứng và soát transcript

Thiết kế toàn bộ giao diện, bao gồm cả luồng cũ và mới: [Figma và danh sách 23 màn hình](web/design/README.md).

## Biên bản có dẫn chứng

- Tóm tắt theo ý, quyết định và việc cần làm có `source_turn_ids`.
- Model phải trả ID có trong phần transcript được cung cấp. Backend kiểm tra ID, lấy timestamp và người nói từ transcript; không dùng timestamp do LLM tự tạo.
- Bấm mốc nguồn để mở đúng lượt nói, xóa bộ lọc đang che lượt đó và nghe audio.
- Nguồn được gắn cờ nhưng chưa soát có nhãn “Nguồn cần soát”. Nội dung chưa rõ có nhãn cần xác nhận; owner/deadline chưa rõ được để trống.
- Có ba mẫu: họp dự án, standup, họp khách hàng. Tạo lại biên bản dùng transcript đã chỉnh sửa.
- Khi nội dung hoặc người nói thay đổi, biên bản cũ được đánh dấu stale; bản export không đưa biên bản stale vào như nội dung hiện tại.
- Transcript dài chia theo lượt nói; lượt quá dài giữ ID trong từng mảnh. Các quyết định/action item và nguồn được giữ khi hợp nhất kết quả.
- Biên bản cũ vẫn đọc được, nhưng không tự gắn dẫn chứng bằng suy đoán.

LLM vẫn cần cấu hình provider/model/key và `llm.enabled`, theo [TESTING.md](TESTING.md). Các kiểm thử dùng provider mô phỏng; chưa đánh giá chất lượng biên bản bằng một provider thật. Kiểm tra ID chỉ xác nhận nguồn tồn tại, không chứng minh lời tóm tắt được nguồn đó hỗ trợ về nghĩa.

## Luồng soát và sửa người nói

- Xác nhận lượt đúng hoặc sửa lời và người nói của từng lượt. Bộ lọc ưu tiên lượt bị gắn cờ theo confidence tăng dần.
- Đổi tên nhóm, gộp các nhóm của cùng một người; lượt đã gán lại vẫn được tính đúng khi gộp.
- Giữ file model gốc, lưu bản chỉnh sửa và lịch sử trong SQLite; nâng cấp database cũ khi khởi tạo.
- Chỉnh sửa kiểm tra revision. Editor giữ revision lúc mở bản nháp để phát hiện thay đổi ở phiên khác.
- Chỉ đánh dấu đã soát không làm biên bản hiện tại thành stale. Việc này cũng không làm biên bản vốn stale trở lại hiện tại.
- Có tiến độ số lượt đã soát, nút đến đoạn cần soát tiếp, tốc độ phát và lặp lượt đang chọn.

| Phím                        | Thao tác                   |
| --------------------------- | -------------------------- |
| Space                       | Phát/tạm dừng              |
| J / L                       | Lùi/tiến 5 giây            |
| N                           | Đến đoạn cần soát tiếp     |
| R                           | Bật/tắt lặp lượt đang chọn |
| Ctrl/⌘ + Enter trong editor | Lưu và đánh dấu đã soát    |

Phím tắt phát audio không chạy khi đang nhập liệu, dùng nút/link hoặc mở dialog.

## Hỏi đáp trong cuộc họp

Tab Hỏi đáp đã có câu trả lời kèm nguồn transcript/audio, lịch sử lưu bền vững, cập nhật theo revision và phản hồi khi thiếu bằng chứng. Xem [AskMeeting và bộ audio nghiệm thu tổng hợp](ASKMEETING.md).

## API bổ sung

- `PATCH /api/jobs/{job_id}/turns/{turn_id}`: thêm `speaker_id`, kết hợp với text/reviewed/expected_revision.
- `POST /api/jobs/{job_id}/speakers/merge`: `source_speaker`, `target_speaker`, `expected_revision`.
- `GET /api/jobs/{job_id}/history`: tối đa 100 thay đổi mới nhất.
- `POST /api/jobs/{job_id}/summary`: body tùy chọn `{"template":"project|standup|customer"}`.
- Result trả speaker ID đã sửa, nguồn có timestamp/trạng thái soát, template và revision của biên bản.

## Kiểm chứng

```bash
uv run --no-sync pytest -q
uv run --no-sync ruff check src/meeting_asr tests
uv run --no-sync ruff format --check src/meeting_asr tests
uv build
cd web
npm run format:check
npm run typecheck
npm run build
npm run test:e2e
```

Bộ kiểm thử bao gồm ID nguồn không hợp lệ, transcript dài, sửa/gộp speaker và persistence, migration database, chỉnh sửa đồng thời khi tạo biên bản, export có dẫn chứng, thao tác nghe/loop, phím tắt, revision conflict và bố cục mobile. Bộ browser dùng API fixture và audio WAV có HTTP range; không coi đây là đánh giá model ASR/LLM.
