# AskMeeting: hỏi đáp trong một cuộc họp

Tab **Hỏi đáp** trả lời từ transcript đã chỉnh sửa. Mỗi ý có ID nguồn, trích đoạn, người nói và nút nghe audio; lịch sử còn sau reload/restart. Khi transcript thay đổi, câu trả lời cũ được đánh dấu và có nút hỏi lại.

## Cách hoạt động

1. Nhận câu hỏi cùng `expected_revision`, tối đa 1000 ký tự.
2. Đọc transcript và revision trong cùng một snapshot SQLite. Truy xuất BM25 theo từ khóa, chuẩn hóa dấu tiếng Việt và một số từ đồng nghĩa như deadline/owner/budget. Lấy thêm lượt liền kề để giữ ngữ cảnh; tìm lượt dài theo các đoạn chồng lấn.
3. Gửi câu hỏi và phần transcript được truy xuất tới provider LLM đã cấu hình cho biên bản. Không gửi bản text gốc đã bị người dùng sửa hoặc metadata ASR dư thừa.
4. Kiểm tra JSON và các ID nguồn. Nguồn/timestamp/trích đoạn lấy từ transcript, không lấy thời gian do model tự tạo. Nguồn chưa soát bị gắn nhãn cần xác nhận.
5. Chỉ lưu câu trả lời khi revision vẫn khớp. Nếu có người sửa trong lúc LLM trả lời, API trả 409 và không lưu kết quả vào sai phiên bản. Câu hỏi trùng trong cùng revision/provider/transcript dùng lại kết quả đã kiểm tra.

Đây là hỏi đáp từng câu độc lập, chưa dùng các câu trả lời trước làm ngữ cảnh hội thoại. Retrieval từ khóa có thể bỏ sót cách diễn đạt khác; “chưa tìm thấy” không chứng minh cả cuộc họp không có đáp án. Kiểm tra ID không chứng minh câu trả lời đúng về nghĩa. Không hiển thị điểm retrieval như xác suất đúng.

## API

`POST /api/jobs/{job_id}/questions`

```json
{ "question": "Ai nhận kiểm thử?", "expected_revision": 0 }
```

Trả `id`, `question`, `revision`, `created`, `stale`, `status` (`found`/`not_found`) và `answer_points`. Mỗi ý có `text`, `source_turn_ids`, `uncertain`, `needs_review`, `sources`. Source chứa `turn_id`, `text`, `speaker`, `start`, `end`, `flagged`, `reviewed` ở thời điểm trả lời.

`GET /api/jobs/{job_id}/questions` trả 20 câu hỏi gần nhất, mới nhất trước. Câu hỏi lặp dùng lại ID/kết quả và cập nhật `created` thành thời điểm hỏi lại để hiện lên đầu lịch sử. Nguồn lịch sử giữ nguyên snapshot; nút nghe mở lượt tương ứng trong transcript hiện tại. Review-only cũng đổi revision và đánh dấu câu trả lời cũ để cập nhật nhãn nguồn.

Health có `ask_enabled`; cấu hình provider/model/key và `llm.enabled` dùng chung với biên bản. Khi LLM tắt, lịch sử vẫn đọc được. Chưa thêm provider mặc định hoặc tự chọn dịch vụ trả phí.

## Audio và bộ nghiệm thu tổng hợp

[Dataset](tests/fixtures/askmeeting.json) có 12 lượt nói, hai speaker, 14 câu hỏi: 8 câu có đáp án và 6 câu thiếu bằng chứng. Các trường hợp gồm owner, deadline bị đính chính, đề xuất chưa chốt, vấn đề còn mở, người phụ trách chưa được giao, ngân sách chưa có số tiền và câu hỏi yêu cầu đoán.

Script tạo giọng tiếng Việt bằng Edge TTS qua module demo hiện có, lưu cache và ghép bản rõ, nhiễu trắng 10 dB, nói chồng. Các bản dùng cùng hội thoại; không phải ba cuộc họp độc lập. Timestamp tham chiếu là khoảng ghép clip TTS, không phải nhãn lời nói người thật. Transcript dùng để kiểm tra hỏi đáp là kịch bản gốc, không phải kết quả ASR.

Chạy từ root sau khi cài dependencies API/demo:

```bash
uv run --no-sync python scripts/askmeeting_demo.py generate
uv run --no-sync python scripts/askmeeting_demo.py evaluate --provider none
uv run --no-sync python scripts/askmeeting_demo.py evaluate --provider fixture
```

Kết quả ở `results/askmeeting-demo/`: audio WAV/MP3/M4A, JSON/RTTM, dataset có thời gian thật của clip và báo cáo từng câu hỏi. `--dataset` và `--directory` cho phép thay dữ liệu/output. Binary audio và báo cáo sinh ra được giữ local.

- `none`: chỉ đánh giá retrieval. Bộ tổng hợp hiện tìm đủ các nguồn chuẩn cho 8/8 câu có đáp án.
- `fixture`: dùng đáp án kịch bản để kiểm tra API/schema/dẫn chứng/abstention; **không đánh giá năng lực LLM**. Chỉ trả đáp án đã định nghĩa và nguồn còn khớp kịch bản. Câu hỏi khác hoặc nguồn đã sửa trả chưa tìm thấy.
- `configured`: chạy provider thật được cấu hình. Báo cáo kiểm tra status và ID nguồn, giữ `semantic_accuracy=null` và các câu trả lời để người đánh giá chấm độ đúng, đủ và hỗ trợ của nguồn.

```bash
uv run --no-sync python scripts/askmeeting_demo.py evaluate --provider configured
```

Chưa chạy đánh giá provider thật trong đợt triển khai này. Không dùng kết quả tổng hợp để kết luận chất lượng ASR, diarization hoặc cuộc họp thật.

## Xem demo và chạy browser qua API thật

```bash
uv run --no-sync python scripts/askmeeting_demo.py serve --provider fixture
```

Demo API chạy ở `127.0.0.1:8001`, dùng SQLite riêng trong `results/askmeeting-demo/jobs/`. Chỉ hỗ trợ bản ghi có sẵn, hỏi đáp và chỉnh sửa; upload/retry/tạo biên bản dùng API chính. Muốn xem thủ công, khởi động FE với `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001` và mở `/?job=ask-demo`. Cần restart FE khi đổi biến này.

Với FE local đang chạy ở port 3000, smoke script chuyển tiếp request sang demo API thật:

```bash
node scripts/smoke_askmeeting_web.mjs
```

Kiểm tra câu trả lời, trích đoạn, seek đúng turn, HTTP audio range 206, câu hỏi thiếu bằng chứng và lịch sử sau reload. Kết quả/screenshot ở cùng thư mục demo. `MEETING_WEB_URL` và `MEETING_ASK_API_URL` đổi địa chỉ server. Demo fixture cần giữ kịch bản ban đầu; dùng thư mục riêng nếu đã sửa nguồn hoặc đổi provider.

## Thiết kế và kiểm thử

[Figma AskMeeting](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=53-2) có 6 trạng thái mới, cộng với 17 màn hình trước thành 23. Navigation Hỏi đáp đã cập nhật trên các màn hình cuộc họp cũ. Xem [danh sách màn hình](web/design/README.md).

Kiểm thử Python bao phủ retrieval, ID giả/trùng, retry, nguồn cần soát, persistence/cache, sửa đồng thời, snapshot DB và thông báo lỗi không chứa transcript. Playwright bao phủ câu trả lời có nguồn, nghe lại, sửa/hỏi lại, thiếu bằng chứng, LLM tắt, revision conflict, pending và mobile.
