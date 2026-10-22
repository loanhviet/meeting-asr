# Baseline ASR dev — 22/10/2026

Chạy DiariZen + DiCoW theo cấu hình mặc định, CUDA/FP16, beam 1, ctc_weight 0, seed 42. LLM tắt; không dùng oracle RTTM. Cả 30 clip thành công.

| Nguồn | Clip | Audio (giây) | WER | CER |
| --- | ---: | ---: | ---: | ---: |
| VietMed dev | 18 | 115.00 | 18.05% | 13.04% |
| FLEURS tiếng Việt dev | 12 | 140.52 | 18.90% | 8.92% |
| Tổng tập thử | 30 | 255.52 | 18.44% | 11.03% |

Chọn 18 clip VietMed (mỗi speaker ID đủ điều kiện một clip) và 12 prompt FLEURS khác nhau, chỉ từ dev, trước khi xem dự đoán. File dưới 5 giây không phù hợp hợp đồng input hiện tại nên không được chọn. Tổng thời gian pipeline từng clip cộng lại: 326.30 giây; gồm khởi tạo subprocess/nạp model từng clip, không phải benchmark thông lượng batch.

WER dùng normalization của project và tách bằng khoảng trắng; tiếng Việt gần đơn vị âm tiết. CER dùng cùng normalization, bỏ space, giữ dấu tiếng Việt. Cộng số edit theo từng clip, không ghép reference/hypothesis qua ranh giới clip. Chấm raw transcript; WER sau hậu xử lý hiện tại bằng raw trên tập này.

Nhãn do nguồn công bố, chưa nghe rà độc lập; không diễn giải thành accuracy cho họp IT hoặc kết quả trên toàn dataset. Không đo DER/cpWER vì thiếu timeline người nói chuẩn cho tập thử. FLEURS dev có toàn bộ nhãn giới tính nguồn là MALE; VietMed có 11 Male/7 Female. Bốn clip VietMed được pipeline dự đoán nhiều hơn một người nói; giữ toàn bộ transcript dự đoán, không chọn người nói bằng đáp án.

## File kết quả

- `selection.json`: dữ liệu và checksum đã chọn.
- `config.yaml`: cấu hình thực nghiệm.
- `summary.json`: số edit, mẫu số và điểm tổng hợp.
- `predictions.jsonl`, `review.csv`: reference và dự đoán từng clip.
- `clips/`: transcript, minutes, RTTM dự đoán, raw output, provenance và run manifest.

## Một số trường hợp để nghe review

### vietmed / utt_id_dev_002309 — WER 72.73%

- Nhãn nguồn: thành ra khi chúng ta nói bệnh dại mà chữa được
- ASR: à xong rồi chúng ta nói quẩn giải chị ma tửa được

### vietmed / utt_id_dev_002435 — WER 63.64%

- Nhãn nguồn: một lúc vào thì là vào đo thì là một trăm bảy hai ạ vâng dạ xuống 172 [hết từ bấy giờ]
- ASR: ra ngoài ngồi một lúc vào thì là nó vào đo thì là một trăm phẩy hai ạ dạ hào từ bộ bảy hai rồi tên bấy giờ

### fleurs_vi / 9936956711547566830.wav — WER 63.16%

- Nhãn nguồn: nằm trong thỏa thuận hợp tác giữa npws và sporting shooters association of australia nsw inc các tình nguyện viên đủ điều kiện đã được tuyển dụng theo chương trình tìm kiếm nhân sự của sporting shooters association
- ASR: nằm trong thỏa thuận hợp tác giữa n b w s và sporting shooter a shop kia teon of australia n s w i n c các tình nguyên viên đủ điều kiện đã đủ tiễn dụng theo chương trình tìm kiếm nhân sự của sporting shooter a shop kia tây xanh

### fleurs_vi / 11157776223844529887.wav — WER 36.67%

- Nhãn nguồn: công viên có diện tích trên 19.500 km² và được chia thành 14 khu sinh thái khác nhau mỗi khu là nơi ở của một hệ động vật hoang dã
- ASR: công viên có diện tích trên mười chín nghìn năm trăm km dôn và được chia thành mười bốn khu sinh thái khác nhau mỗi khu là nơi ở của một hài động vật ngoan dã

### fleurs_vi / 7985674771975971897.wav — WER 30.77%

- Nhãn nguồn: tổng thống mỹ george w bush nhiệt liệt hoan nghênh thông báo này
- ASR: tổng thống mỹ josh boot niệt liệt hoan nghênh thông báo này
