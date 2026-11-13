# Thử hiệu chỉnh ASR với Kimi K3

Nhánh: `feat/contextual-asr-correction`. Model yêu cầu: `kimi-k3`.

Luồng đã có: transcript ASR → API Kimi → gợi ý sửa cụm ngắn → kiểm tra bằng code → artifact riêng để review. Lệnh CLI dùng được với `transcript.json` hoặc `minutes.json`. Đầu vào gốc được giữ nguyên, kết quả ghi trạng thái `suggestions_only`; chưa có nút chấp nhận gợi ý trên web.

## Gọi từ CLI

```sh
.venv/bin/meeting-asr correct-transcript results/demo/transcript.json \
  --api-key-csv /path/to/api-key.csv \
  --model kimi-k3 \
  --context 'Cuộc họp kỹ thuật về triển khai phần mềm.' \
  --out results/demo/correction-suggestions.json \
  --cache-dir results/demo/correction-cache
```

File API CSV là bản export key/value của Alibaba Cloud: có hàng `apiKey` và `openAiCompatible`. Adapter đọc khóa trong bộ nhớ; kết quả/cache không chứa khóa. Cần giữ file credential bên ngoài repo. Adapter không dùng cấu hình hoặc khóa tóm tắt cũ trong `.env`.

`--glossary /path/terms.json` nhận một mảng JSON các thuật ngữ có sẵn trước khi đọc đáp án, tối đa 100 mục. Ví dụ: `["Docker", "React", "useEffect"]`. Glossary cung cấp ứng viên, không xác minh từ đó xuất hiện trong audio. File `configs/correction-glossary.vi.json` là bản đồ thuật ngữ theo dataset dành cho script so sánh, không phải mảng đầu vào CLI.

`kimi-k3` được kiểm tra có trong danh sách model của endpoint ở file CSV. Đã gọi canary thành công và nhận đúng model ID. Dùng endpoint `openAiCompatible` do CSV cung cấp, không đổi sang một nhà cung cấp khác.

Theo [tài liệu Kimi của Alibaba Cloud](https://help.aliyun.com/zh/model-studio/kimi-api), K3 dùng chế độ suy luận, không tắt được bằng `enable_thinking` và không hỗ trợ `thinking_budget`. Adapter dùng Chat Completions, JSON mode, `enable_thinking: true`, giới hạn output mặc định 4.096 token. Reasoning token được tính trong usage; không lưu `reasoning_content`. Giới hạn này có thể khiến câu trả lời bị cắt; phản hồi không hoàn tất được coi là lỗi và không trở thành gợi ý hợp lệ.

## Kiểm tra gợi ý

- Chỉ nhận `turn_id` đã gửi và danh sách edit có đúng `before`, `after`, `reason`.
- `before` phải khớp nguyên văn, xuất hiện duy nhất, không nằm giữa một từ. Offset tính bằng Python trên text nguồn, không yêu cầu model đếm ký tự tiếng Việt.
- Tối đa 3 edit/lượt; mỗi cụm trước/sau tối đa 6 đơn vị cách nhau bằng space. Patch không chồng nhau.
- Chặn thay đổi chữ số, một số từ chỉ số, phủ định và mức độ cam kết (`đã`, `sẽ`, `có thể`...). Kiểm tra cả cụm lẫn toàn câu để phát hiện tác động qua ranh giới patch.
- Giới hạn phần ký tự thay đổi ở mức 35%; đây là ngưỡng thí nghiệm đặt trước, chưa được calibration.
- Mỗi gợi ý giữ SHA256 và nguyên văn nguồn. Không có bước tự đổi speaker, timestamp, sửa tay hay tóm tắt hiện có.
- Cache phụ thuộc nội dung prompt, context, glossary, model, endpoint, phiên bản prompt và giới hạn token. Đổi text nguồn làm đổi cache key.

Các kiểm tra trên giới hạn phạm vi sửa, **không chứng minh bản sửa đúng nghĩa hoặc đúng audio**. Tên riêng vẫn có thể bị đoán sai; heuristic từ chỉ số/phủ định có thể chặn một sửa hợp lý. Gợi ý hợp lệ về cấu trúc vẫn cần review trước khi trở thành transcript được chấp nhận.

## Thử nghiệm trên baseline dev đã đóng băng

Baseline được lưu ở `results/asr-baseline-20261022/dev_v1/` và mô tả tại [ASR_BASELINE_2026-10-22.md](ASR_BASELINE_2026-10-22.md). Có 18 clip VietMed + 12 clip FLEURS, tổng 255,52 giây; WER 18,44%, CER 11,03%. Tất cả là dev; nhãn do nguồn công bố, chưa nghe rà độc lập trong project.

```sh
.venv/bin/python scripts/compare_llm_correction.py \
  --baseline results/asr-baseline-20261022/dev_v1 \
  --api-key-csv /path/to/api-key.csv \
  --out results/kimi-k3-asr-20261022/comparison_v1 \
  --workers 3
```

Ba đầu ra so sánh:

1. ASR gốc đã lưu, không chạy nhận diện lại.
2. Kimi sửa text với ngữ cảnh miền ngắn, không glossary (`text`).
3. Cùng prompt và ngữ cảnh, thêm 20 thuật ngữ y tế tổng quát cho VietMed (`glossary`). Không lấy danh sách thực thể từ đáp án. FLEURS không có glossary nên có thể tái sử dụng cùng phản hồi cache; hai kết quả đó không phải hai lượt sinh độc lập.

Model chỉ nhận ID, hypothesis, mô tả miền và glossary. `inference_inputs.jsonl` lưu đúng các trường này; reference chỉ xuất hiện trong file chấm sau phản hồi. Không gửi audio, đáp án, đoạn chuẩn lân cận, hay gợi ý tên từ gold vào API.

Kết quả nằm trong thư mục `comparison_v1`: `experiment.json`, `summary.json`, `results.jsonl`, các file từng clip theo variant, cache và `inference_inputs.jsonl`. Báo cáo thực đo được tạo sau lượt chạy, không điền số giả định vào bảng.

Tạo lại phân tích và bảng review từ phản hồi đã lưu, không gọi API:

```sh
.venv/bin/python scripts/report_llm_correction.py \
  --baseline results/asr-baseline-20261022/dev_v1 \
  --run results/kimi-k3-asr-20261022/comparison_v1 \
  --document document/KIMI_ASR_EXPERIMENT_2026-10-22.md
```

Phân tích chính nằm ở `analysis_summary.json` và `analysis_rows.jsonl`: nếu glossary rỗng thì giữ cùng phản hồi text, kể cả lỗi, để tránh nhầm biến động sinh ngẫu nhiên với tác dụng glossary. Các lượt gọi lặp vẫn nằm trong artifact raw và được tính vào thống kê usage quan sát. Script từ chối ghi đè một phép so sánh đã hoàn tất; dùng output directory mới cho lượt thử khác.

WER/CER tính giống baseline, cộng edit theo từng clip. Báo thêm số clip giảm/tăng lỗi, số câu ASR vốn đúng bị làm sai, số patch bị chặn, usage và độ trễ. “Patch được chấp nhận” trong số liệu chỉ có nghĩa qua validator để tạo bản đề xuất dùng chấm giả định, không phải được người nghe xác minh. Nếu API lỗi, giữ hypothesis gốc và tính clip đó vào mẫu số, đồng thời đánh dấu lỗi.

Khi một phản hồi API bị lỗi nhưng có trả usage, code lưu metadata usage để theo dõi. Nếu service timeout/không trả usage, số token quan sát được chưa phải toàn bộ hóa đơn. Không tự suy ra giá tiền từ số token nếu chưa đối chiếu bảng giá endpoint/tài khoản.

## Điều kiện trước khi mở rộng

Tập nhỏ này giúp kiểm tra khả năng tích hợp và hành vi giữ nguyên/sửa sai. Cần nghe rà các gợi ý thay đổi nghĩa, thử thêm recording độc lập và gold họp IT, chọn ngưỡng/prompt trên dev rồi mới chấm test giữ riêng. WER giảm không tự chứng minh ít lỗi quan trọng hơn hoặc tiết kiệm thời gian review.
