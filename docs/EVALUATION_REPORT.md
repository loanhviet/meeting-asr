# Tóm tắt chất lượng ASR và diarization

Tổng hợp báo cáo đã có, không chạy lại model. Test phần mềm mới nằm ở
[TEST_REPORT.md](TEST_REPORT.md); phạm vi test ở [TEST_PLAN.md](TEST_PLAN.md).

## Dữ liệu và thước đo

- Nhãn do nguồn công bố, chưa được nhóm nghe rà độc lập. Kho gồm lời đọc,
  giọng vùng miền, y tế, hội thoại và họp; không đồng nhất thành bộ họp tiếng
  Việt đã nghiệm thu. [Nguồn dữ liệu](https://github.com/loanhviet/meeting-asr/blob/0b641e4/document/EVALUATION_DATA_2026-10-22.md).
- WER: lỗi thay/chèn/xóa trên reference sau normalization, tách whitespace
  nên tiếng Việt gần đơn vị âm tiết. CER bỏ space, giữ dấu. DER tính lỗi
  miss/false alarm/confusion theo speaker-time, có UEM và quy ước collar/overlap.
  [Protocol](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md).
- cpWER tìm hoán vị speaker tốt nhất; tcpWER thêm ràng buộc thời gian.
  Không lấy cpWER trừ WER làm lỗi diarization.
  [Quy trình scorer](experiments/ASR_IMPROVEMENT_WORKFLOW.md).

## Điểm nền chẩn đoán

DiariZen + DiCoW pretrained, beam 1, LLM tắt, không oracle; mỗi dòng có nguồn
cho cả cỡ mẫu và điểm. Các miền được báo riêng.

| Dữ liệu đã chấm | WER | CER | Nguồn |
|---|---:|---:|---|
| FLEURS VI test subset, 40 clip | 14,94% | 8,82% | [Báo cáo họp](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md) |
| ViMD test diagnostic, 63 clip | 20,82% | 12,07% | [Báo cáo họp](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md) |
| VietMed pilot test, 27 clip | 24,19% | 17,68% | [Báo cáo họp](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md) |
| COSV Đức–Ly, toàn recording | 29,17% | 21,91% | [Báo cáo họp](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md) |

| Diarization | DER | Quy ước | Nguồn |
|---|---:|---|---|
| ViYT-Diar, toàn bộ 100 file | 14,07% | Strict: collar 0, giữ overlap | [Báo cáo họp](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md) |
| Cùng 100 file | 7,83% | Relaxed: collar 0,25 giây, bỏ overlap | [Báo cáo họp](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md) |

ViYT không có transcript để chấm WER/CER/cpWER. COSV thiếu timestamp/speaker
đủ tin cậy để chấm DER/cpWER, nên điểm text là thăm dò.
[Giới hạn nhãn](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md).

## Baseline và phương án cải thiện

Các cặp dưới đây dùng cùng dữ liệu trong từng lượt; không so trực tiếp điểm
giữa các lượt khác tập dev.

| Thí nghiệm | Baseline → phương án thử | Kết quả | Nguồn |
|---|---|---|---|
| Decoding dev: 20 FLEURS + 20 VietMed | DiCoW beam 1 → beam 3 | FLEURS WER 14,49% → 14,49%; VietMed 23,49% → 23,28%; chỉ giảm 1 lỗi tổng | [Vòng cải thiện](experiments/ASR_IMPROVEMENT_ROUND1_2026-10-26.md) |
| Cùng lượt, AMI ES2011a dev tiếng Anh | Beam 1 → beam 3 | tcpWER 24,00% → 22,55%; DER không đổi: strict 12,67%, relaxed 8,13% | [Vòng cải thiện](experiments/ASR_IMPROVEMENT_ROUND1_2026-10-26.md) |
| Sửa bằng LLM: 30 clip dev FLEURS/VietMed | ASR gốc → Kimi + context | WER 18,44% → 16,58%; CER 11,03% → 10,42% | [Kimi](https://github.com/loanhviet/meeting-asr/blob/0b641e4/document/KIMI_ASR_EXPERIMENT_2026-10-22.md) |
| Cùng 30 clip dev | ASR gốc → Kimi + context + glossary | WER 18,44% → 16,98%; CER 11,03% → 10,53% | [Kimi](https://github.com/loanhviet/meeting-asr/blob/0b641e4/document/KIMI_ASR_EXPERIMENT_2026-10-22.md) |

Beam 3 chỉ là ứng viên dev; mặc định giữ beam 1. Kimi là bản sửa giả định
qua validator, chưa được người nghe chấp nhận; lỗi API giữ ASR gốc trong mẫu số.
Không có lượt fine-tune trong các phép thử trên. [Vòng cải thiện](experiments/ASR_IMPROVEMENT_ROUND1_2026-10-26.md),
[Kimi](https://github.com/loanhviet/meeting-asr/blob/0b641e4/document/KIMI_ASR_EXPERIMENT_2026-10-22.md).

## Điểm yếu và TODO

- Beam 5 lặp text trên AMI, WER 185,82%; bị loại. CER tiếng Việt còn tăng nhẹ
  khi đổi beam 1 sang 3. [Nguồn](experiments/ASR_IMPROVEMENT_ROUND1_2026-10-26.md).
- Microphone phòng và vùng giọng khó cần kiểm tra thêm; AMI là tiếng Anh,
  có trong training theo model card được báo cáo, không chứng minh tổng quát
  tiếng Việt. [Nguồn](experiments/GENERAL_MEETING_EVALUATION_2026-10-26.md).
- TODO: nghe rà các file ViYT bị đánh dấu và reference COSV; bổ sung bộ họp
  tiếng Việt nhiều người/nói chồng, tách dev/test theo recording.
  [Việc còn lại](https://github.com/loanhviet/meeting-asr/blob/0b641e4/document/GENERAL_MEETING_PLAN_2026-10-26.md).
- TODO: đo cải thiện DER, calibration confidence và công nghe sửa trên bộ
  nghiệm thu; chưa có số trước/sau được xác nhận cho các mục này.
  [Kế hoạch](https://github.com/loanhviet/meeting-asr/blob/0b641e4/document/GENERAL_MEETING_PLAN_2026-10-26.md).
- TODO: nghiệm thu semantic summary/QA; canary của lượt cải thiện bị chặn quota,
  chưa có semantic score trong lượt đó. [Nguồn](experiments/ASR_IMPROVEMENT_ROUND1_2026-10-26.md).
