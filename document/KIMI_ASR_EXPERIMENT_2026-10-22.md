# Thử hiệu chỉnh ASR bằng Kimi K3 — 22/10/2026

Nhánh: `feat/contextual-asr-correction`. Dùng API Alibaba Cloud với đúng model `kimi-k3`; key đọc từ CSV của người dùng. Không lưu key trong code/artifact.

30 clip dev (12 fleurs_vi, 18 vietmed), 255.52 giây. ASR DiariZen + DiCoW đã đóng băng trước khi gọi LLM. Không dùng test, không gửi audio hoặc reference vào model. Nhãn nguồn chưa được nghe rà độc lập.

## Kết quả chính

| Phương án | WER | CER | Clip giảm lỗi | Clip tăng lỗi | Clip thiếu phản hồi hợp lệ |
| --- | ---: | ---: | ---: | ---: | ---: |
| ASR gốc | 18.44% | 11.03% | — | — | 0 |
| Kimi + ngữ cảnh miền | 16.58% | 10.42% | 8 | 1 | 3 |
| Kimi + ngữ cảnh + glossary | 16.98% | 10.53% | 6 | 1 | 5 |

API lỗi được giữ nguyên ASR và vẫn tính vào mẫu số; số clip thiếu phản hồi ở phương án glossary gồm cả các phản hồi text lỗi được dùng lại khi glossary rỗng. Các bản sửa được chấm là gợi ý giả định qua validator, chưa được người nghe chấp nhận.

## Theo nguồn

| Nguồn | Phương án | WER | CER |
| --- | --- | ---: | ---: |
| vietmed | ASR gốc | 18.05% | 13.04% |
| vietmed | text | 16.10% | 12.59% |
| vietmed | glossary | 16.83% | 12.82% |
| fleurs_vi | ASR gốc | 18.90% | 8.92% |
| fleurs_vi | text | 17.15% | 8.14% |
| fleurs_vi | glossary | 17.15% | 8.14% |

Glossary gồm 20 thuật ngữ y tế tổng quát, không lấy thực thể từ gold. FLEURS có glossary rỗng, nên phân tích chính dùng lại phản hồi `text`, kể cả lỗi API. Các phản hồi gọi lặp cùng prompt vẫn giữ trong artifact raw; không quy thay đổi do lượt sinh ngẫu nhiên thành lợi ích glossary.

## Lỗi mới cần review

- `text`: khôi phục 11 đơn vị reference nhưng làm sai 3 đơn vị vốn khớp; 0 clip có baseline đúng hoàn toàn bị tăng WER. Các số này dựa trên alignment, không tính lỗi chèn mới và không thay thế nghe rà.
- `glossary`: khôi phục 10 đơn vị reference nhưng làm sai 3 đơn vị vốn khớp; 0 clip có baseline đúng hoàn toàn bị tăng WER. Các số này dựa trên alignment, không tính lỗi chèn mới và không thay thế nghe rà.

### text / 17343506464706503834.wav

- Nhãn nguồn: các ca sĩ nổi tiếng trên khắp cả nước trình bày bhajan hoặc các bài hát mộ đạo tại chân của shri shyam
- ASR: các ca sĩ nổi tiếng trên khắp cả nước trình bài hajan hoặc các bài hát mộ đạo tại chân của sri sam
- Gợi ý Kimi: các ca sĩ nổi tiếng trên khắp cả nước trình bài hajan hoặc các bài hát mộc mạc tại chân của sri sam
- Đơn vị vốn đúng bị đổi: mộ, đạo.

### text / 874493660479990758.wav

- Nhãn nguồn: công nghệ cung ứng giải pháp bằng các chuyến đi thực tế ảo sinh viên có thể xem các hiện vật bảo tàng tham quan hồ thủy sinh hoặc chiêm ngưỡng tác phẩm đẹp trong khi ngồi trong lớp
- ASR: công nghệ cung ứng giải pháp bằng các chuyến đi thực tế ảo sinh viên có thể xem các hiện vật bảo tàng tham quan hồ thủy sinh hoặc chim ngưỡng tác phẩm đẹp trong khi ngồi trong lớp
- Gợi ý Kimi: công nghệ cung ứng giải pháp bằng các chuyến đi thực tế ảo sinh viên có thể xem các hiện vật bảo tàng tham quan hồ thủy cung hoặc chiêm ngưỡng tác phẩm đẹp trong khi ngồi trong lớp
- Đơn vị vốn đúng bị đổi: sinh.

### glossary / 17343506464706503834.wav

- Nhãn nguồn: các ca sĩ nổi tiếng trên khắp cả nước trình bày bhajan hoặc các bài hát mộ đạo tại chân của shri shyam
- ASR: các ca sĩ nổi tiếng trên khắp cả nước trình bài hajan hoặc các bài hát mộ đạo tại chân của sri sam
- Gợi ý Kimi: các ca sĩ nổi tiếng trên khắp cả nước trình bài hajan hoặc các bài hát mộc mạc tại chân của sri sam
- Đơn vị vốn đúng bị đổi: mộ, đạo.

### glossary / 874493660479990758.wav

- Nhãn nguồn: công nghệ cung ứng giải pháp bằng các chuyến đi thực tế ảo sinh viên có thể xem các hiện vật bảo tàng tham quan hồ thủy sinh hoặc chiêm ngưỡng tác phẩm đẹp trong khi ngồi trong lớp
- ASR: công nghệ cung ứng giải pháp bằng các chuyến đi thực tế ảo sinh viên có thể xem các hiện vật bảo tàng tham quan hồ thủy sinh hoặc chim ngưỡng tác phẩm đẹp trong khi ngồi trong lớp
- Gợi ý Kimi: công nghệ cung ứng giải pháp bằng các chuyến đi thực tế ảo sinh viên có thể xem các hiện vật bảo tàng tham quan hồ thủy cung hoặc chiêm ngưỡng tác phẩm đẹp trong khi ngồi trong lớp
- Đơn vị vốn đúng bị đổi: sinh.

## Vận hành và kiểm tra

Có 50 lời gọi không lấy từ cache, 44 có usage được lưu. Quan sát 33927 input token và 49348 output token (gồm suy luận), tổng 83275. 6 phản hồi lỗi không có usage trong artifact lượt này; đây không phải tổng hóa đơn.

Độ trễ các lời gọi thành công có metadata: p50 16.87s, p95 74.27s. Không tính timeout/không có metadata vào các percentile này.

Kiểm tra hash baseline và các trường payload đã được thực hiện khi tạo báo cáo. Kết quả kiểm thử phần mềm/kiểm tra credential được lưu riêng trong `software_validation.json` của lượt chạy.

## File và cách đọc

- `analysis_summary.json`, `analysis_rows.jsonl`, `review.csv`: phân tích chính.
- `summary.json`, `results.jsonl`, thư mục `text/`, `glossary/`: kết quả raw đầy đủ.
- `inference_inputs.jsonl`: dữ liệu thực sự gửi vào model, không có đáp án.
- `cache/`: proposal và metadata, không có credential hoặc reasoning_content.

Kết quả này chưa đủ để tự động áp dụng sửa hoặc kết luận hiệu quả trên họp IT. Bước tiếp theo là nghe rà các patch, thử gold họp IT và recording độc lập, rồi chốt prompt/ngưỡng trên dev trước khi chấm test.

API/model: [tài liệu chính thức Alibaba Cloud Kimi](https://help.aliyun.com/zh/model-studio/kimi-api).
