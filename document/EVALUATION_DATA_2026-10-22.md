# Kho dữ liệu đánh giá ASR, diarization và LLM

Thu gom ngày 22/10/2026. Thư mục dữ liệu: `data/gold/vi_asr_v1/`.

Đã thu gom **9 nguồn**, trong đó mở rộng/tải mới 6 nguồn và lập chỉ mục lại 3 nguồn có sẵn. Tổng audio trong các manifest là **30,36 giờ**, chưa cộng lặp pilot/đoạn xuất thử. Tải từ mạng **39 file, 7.441.657.284 byte (~6,93 GiB)**; cả kho sau giải nén và xuất pilot khoảng **8,9 GiB**. Không chạy mô hình nhận diện, không gọi API LLM, không đổi cấu hình ứng dụng.

Đây là **nhãn tham chiếu do nguồn công bố**, chưa được người trong project nghe rà độc lập. Có thể chấm benchmark theo quy ước của từng nguồn; không gọi tất cả là gold đã được project xác minh. Thư mục `gold` là nơi quản lý kho đánh giá, không phải chứng nhận chất lượng từng hàng.

## Các bộ đã có trên máy

| Nguồn | Phần đã thu gom thực tế | Phù hợp để đánh giá | Giới hạn chính |
| --- | --- | --- | --- |
| [VietMed](https://huggingface.co/datasets/leduckhai/VietMed) | Dev + test đầy đủ: **6.349 cặp audio–text, 10,98 giờ**; 48 nhãn người nói | WER/CER, tác động của LLM lên lỗi thuật ngữ, độ bền theo giọng/điều kiện thu | Nội dung y tế, không thay thế họp IT. Các utterance không tự tạo thành hội thoại liên tục. |
| [ViMD](https://huggingface.co/datasets/nguyendv02/ViMD_Dataset) | Test đầy đủ, 14 shard: **2.026 cặp, 10,87 giờ, 63 tỉnh, 1.344 speaker ID** | WER/CER theo vùng, tỉnh, người nói; lỗi gần âm | Nguồn chương trình phát thanh/truyền hình, không phải bộ họp nhiều người có RTTM. Chưa tải train/valid. |
| [FLEURS tiếng Việt](https://huggingface.co/datasets/google/fleurs) | Dev **361** + test **857** = **1.218 cặp, 4,20 giờ** | Đối chứng ASR lời đọc; số, tên, từ ngoại lai; lỗi mới sau LLM | Không có ID người nói trong TSV này; không chứng minh speaker-disjoint. |
| [VIVOS](https://huggingface.co/datasets/AILAB-VNUHCM/vivos) | Toàn bộ official test đang có: **760 cặp, 44,76 phút, 19 người nói** | Đối chứng tiếng Việt sạch, phát hiện LLM sửa hỏng đoạn đúng | Dự án đã dùng và chia lại 120 dev / 640 test; giữ `project_previous_split`, không coi đây là bộ test mới chưa đụng tới. |
| [ViYT-Diar](https://huggingface.co/datasets/tuanduy1612/ViYT-Diar) | Test đầy đủ: **100 audio, 104,32 phút**, RTTM + UEM | DER, speech activity và overlap từ nhãn người nói | **Không có transcript**: không chấm WER/CER hoặc cpWER. Metadata giấy phép giữ theo dataset card. |
| [COSV–CVP](https://cosv.ortolang.fr/le-corpus/) | Hai phỏng vấn nhóm đã có: **106,27 phút**, transcript thủ công nguồn | WER/CER thăm dò trên hội thoại tự nhiên; sửa theo ngữ cảnh | Transcript thiếu timestamp, còn nhãn speaker mơ hồ. Chấm toàn recording với toàn transcript; chưa chấm DER/cpWER. |
| [AMI ES2004a](https://groups.inf.ed.ac.uk/ami/download/) | Đoạn họp **179,105 giây**, 4 người, manual transcript + RTTM/UEM đã có | Kiểm tra pipeline WER/cpWER/DER nhiều người, nói chồng | **Tiếng Anh**, Mix-Headset; AMI được model card DiCoW nêu trong dữ liệu huấn luyện. Báo riêng. |
| [VietMed-Sum](https://huggingface.co/datasets/leduckhai/VietMed-Sum) | **3.597 hàng transcript–summary**: dev 1.568, test 2.029; thêm **1.952 hàng đầu vào ASR** ở các biến thể test | Tóm tắt tiếng Việt từ transcript sạch hoặc nhiễu | Các biến thể local/global không phải các cuộc họp độc lập. GOLD được người sửa từ gợi ý LLM, gồm hội thoại thực và mô phỏng theo paper; chưa được project rà. |
| [QMSum](https://github.com/Yale-LILY/QMSum) | Toàn bộ train/val/test: **232 cuộc họp, 1.810 query–answer** đếm từ file tải; có evidence spans cho specific queries | Hỏi đáp theo transcript, tìm bằng chứng, tóm tắt theo câu hỏi | **Tiếng Anh, chỉ text trong phần thu gom này**, không chấm ASR. Đếm thực tế ở revision đã pin là 1.810, khác số 1.808 nêu trong giới thiệu paper; giữ nguyên nguồn. |

Số giờ trên là thời lượng audio của từng mục, không phải số giờ họp tiếng Việt đồng nhất. Không gộp các bộ thành một điểm chất lượng rồi suy ra hiệu quả trên họp IT.

## Cấu trúc và cách đọc

```text
data/gold/vi_asr_v1/
  catalog.json                   # Danh mục nguồn, tác vụ và phạm vi
  source_lock.json               # URL bất biến, revision, số byte, SHA256
  downloads.json                 # Nhật ký tải và checksum
  audit.json                     # Thống kê, phạm vi nhãn, split pilot
  validation.json                # Kết quả kiểm tra dữ liệu thực tế
  sources/                       # File nguồn gốc, dataset card, parquet/tar/TSV
  audio/                         # Audio đã xuất hoặc chuyển PCM16
  manifests/<dataset>/           # Nhãn nguồn + metadata + vị trí audio
  inputs/<dataset>/              # Đầu vào mô hình, không có trường đáp án
  references/<dataset>/          # RTTM/UEM hoặc đáp án tóm tắt/QMSum
  pilot/                         # Bộ thử hiệu chỉnh ASR gần 60 phút
  exports/vimd_diagnostic/       # 126 WAV nguồn, đủ 63 mã tỉnh
  review/uit_it/                 # 6 đoạn họp IT đang chờ chép nhãn
```

Các đường dẫn trong JSONL tính từ **gốc kho `data/gold/vi_asr_v1/`**, không tính từ thư mục chứa JSONL. VIVOS, COSV và AMI trỏ về file local có sẵn bằng đường dẫn tương đối; không nhân bản audio. Giữ nguyên cấu trúc repo khi di chuyển.

- Audio VietMed đầy đủ đã xuất thành OGG gốc; cần chuyển sang WAV trước khi chạy CLI vì bộ lọc đầu vào hiện chỉ nhận WAV/MP3/M4A. Pilot đã có WAV PCM16 sẵn. FLEURS giữ WAV gốc, có thể là float32; pipeline giải mã WAV qua FFmpeg. CLI hiện yêu cầu mỗi file dài ít nhất 5 giây, nên cần ghi rõ các clip ngắn hơn bị loại khi chọn tập thử.
- ViYT-Diar đã xuất WAV mono PCM16 16 kHz. Sample count giữ nguyên, RTTM chuyển trực tiếp từ nhãn nguồn; UEM phủ toàn audio.
- **Audio ViMD đầy đủ nằm trong parquet**. Manifest có `audio_locator` gồm tên parquet và row; `audio_path: null` nghĩa là chưa xuất riêng, không phải thiếu audio. 126 mẫu chẩn đoán đã xuất WAV nguyên byte và bao phủ đủ 63 mã tỉnh, tổng 41,57 phút. Đây không phải kết quả benchmark toàn bộ test.
- `reference_text` dùng cho chấm ASR; `source_fields` giữ nguyên hàng của bộ text. Đầu vào tóm tắt dùng trường `transcript`; QMSum dùng `query` và `meeting_transcripts`. Không đưa manifest chứa đáp án vào prompt hiệu chỉnh.
- Chưa sinh dự đoán ASR cho các bộ mới, nên chưa có cặp **ASR sai → transcript đúng** để huấn luyện/chấm bộ sửa. Bước đó cần chạy ASR cố định trước, lưu dự đoán riêng rồi đối chiếu nhãn.

## Pilot đề xuất để bắt đầu với LLM

Đã tạo từ VietMed, lấy mẫu trước khi biết đầu ra mô hình:

| Split | Clip | Thời lượng | Recording | Speaker ID |
| --- | --- | --- | --- | --- |
| Dev | 308 | 30 phút 01 giây | 9 | 19 |
| Test | 288 | 30 phút 03 giây | 14 | 27 |

- Audio PCM16: `pilot/audio/dev/`, `pilot/audio/test/`.
- Chạy nhận diện từ `pilot/inputs/dev.jsonl` và `test.jsonl`.
- Đáp án nguồn: `pilot/references/dev.jsonl` và `test.jsonl`.
- Phiếu nghe rà: `pilot/review_dev.csv`, `review_test.csv`; trạng thái ban đầu `pending`. Script không ghi đè CSV đã có khi tạo lại.
- Chọn round-robin theo speaker, seed 42, không lọc theo lỗi ASR. Đây là pilot chẩn đoán, không khẳng định đại diện phân bố triển khai.
- **Không trùng recording ID và speaker ID giữa dev/test pilot** theo metadata nguồn. Official dev/test của VietMed cùng chứa `VietMed_019`, nhưng speaker ID khác nhau. Giữ nguyên official split trong kho; bỏ recording này khỏi dev của pilot, giữ trong test. Không tự tuyên bố nguồn làm sai split người nói.
- Dataset card VietMed thông báo sửa mismatch audio–transcript vào tháng 10/2026. Đã pin revision `f302146...`, lưu card và checksum; kết quả trên phiên bản này không tự so được với số cũ trong paper.

## Bộ họp IT sát sản phẩm

Đoạn UIT đang có trong project dài 180 giây, nguồn video `gdBil7QZ4hg`, trích 02:00–05:00. Đã chia thành 6 khoảng lõi 30 giây, thêm tối đa 2 giây ngữ cảnh mỗi bên, kèm `review/uit_it/reference_template.json` và `review.csv`.

**Chưa có transcript chuẩn**, nên các đoạn này không tính vào số audio có nhãn ở trên và không được dùng chấm điểm. Thời gian chia clip là ranh giới công việc, không phải nhãn speech/turn. Chép theo khoảng lõi, nghe thêm bản liên tục khi từ vắt qua ranh giới; cần gán speaker nhất quán và rà nói chồng nếu muốn DER/cpWER.

## Kiểm tra đã thực hiện

- 39 file tải đã đối chiếu đầy đủ số byte và SHA256; revision/URL được pin. Không dùng bản mirror VietMed khác phiên bản.
- Đã đọc toàn bộ 14 shard test ViMD, kiểm tra WAV headers và số lượng mẫu; xác nhận đủ 63 mã tỉnh trong phần đã tải.
- Toàn bộ 1.218 audio FLEURS khớp sample count 16 kHz trong TSV. Giữ nguyên dấu ngoặc kép trong lời nói bằng parser TSV không coi chúng là ký hiệu trích dẫn CSV.
- Toàn bộ ViYT-Diar có số start/end/speaker khớp, mốc thời gian hợp lệ trong thời lượng audio; PCM conversion giữ sample count.
- VIVOS test prompts local khớp nguyên byte với file công bố ở revision đã pin.
- Không thấy trùng checksum audio gốc giữa dev/test của VietMed và FLEURS; FLEURS không trùng prompt ID giữa hai split. Không suy ra đã loại mọi trùng lặp qua mã hóa lại.
- QMSum không trùng nguyên transcript cuộc họp giữa train/val/test theo hash; inputs không chứa đáp án hoặc evidence spans. QMSum có nguồn gốc AMI/ICSI, nên không coi các nguồn đó là độc lập chỉ vì tên dataset khác nhau.
- Đây là kiểm tra cấu trúc và provenance; **chưa phải điểm chất lượng mô hình, kiểm chứng từng chữ bằng nghe, hoặc bảo đảm độc lập với dữ liệu pretraining**.

## Tái sử dụng và xuất audio

App venv giữ nguyên. PyArrow 23.0.1 được cài trong môi trường công cụ riêng `.cache/gold-tools/venv`; FFmpeg dùng bản có sẵn trên máy.

```sh
# Tải lại/kiểm tra file đã tải theo lock hiện có; không tải model.
.venv/bin/python scripts/collect_evaluation_data.py \
  data/gold/vi_asr_v1/source_lock.json --workers 3

# Lập lại manifest và pilot. Cần các file VIVOS/COSV/AMI local được nêu trên.
.cache/gold-tools/venv/bin/python scripts/prepare_evaluation_data.py \
  data/gold/vi_asr_v1

# Xuất toàn bộ ViMD test thành WAV nguồn nếu cần chạy batch (tốn thêm dung lượng).
.cache/gold-tools/venv/bin/python scripts/export_evaluation_audio.py \
  data/gold/vi_asr_v1 --manifest manifests/vimd/test.jsonl \
  --out exports/vimd_full_test
```

Thêm `--limit 126` để xuất một tập chẩn đoán cân bằng số mẫu giữa các mã tỉnh. Bản lock dự phòng nằm ở `document/evaluation_data_sources_2026-10-22.lock.json`; khi dựng kho mới, chép lock vào gốc kho trước khi tải. Các file lớn trong `data/` bị git ignore theo quy ước repo.

## Quy ước đánh giá tiếp theo

1. Chạy ASR với cấu hình/phiên bản cố định, LLM tóm tắt tắt, lưu dự đoán gốc riêng. Không đưa reference RTTM vào luồng end-to-end.
2. Chỉnh prompt/bộ sửa bằng dev; giữ test cho lượt chấm cuối. Với ViMD chỉ thu gom official test, không dùng toàn test để chỉnh prompt rồi báo đó là đánh giá giữ riêng.
3. Chuẩn hóa tiếng Việt giống nhau cho reference và hypothesis; ghi rõ WER hiện dùng khoảng trắng, gần đơn vị âm tiết, thêm CER. Giữ bản transcript gốc trước normalization.
4. So sánh ASR gốc và ASR + LLM trên cùng audio, đếm cả lỗi mới, lỗi số/tên/phủ định, thời gian review và chi phí. Chỉ sửa hoa/thường hoặc dấu câu cần báo riêng.
5. DER phải công bố collar, overlap policy và UEM. Không tính DER từ thời gian dự đoán/forced alignment chưa xác minh. Không dùng speaker ID cấp clip để suy ra diarization timeline.
6. ROUGE/đáp án nguồn hỗ trợ đánh giá tóm tắt, nhưng cần rà factuality/evidence và lỗi đổi nghĩa. QMSum là tóm tắt theo câu hỏi, không bao phủ mọi hành vi AskMeeting như câu hỏi không có đáp án hoặc lọc thời gian.
7. Mở rộng gold họp IT bằng nghe chép và kiểm tra độc lập; public corpus khác miền chỉ là các trục đánh giá bổ sung.

## Nguồn và giấy phép được lưu

Dataset cards, URL và revision nằm trong `sources/`, `source_lock.json` và `catalog.json`. FLEURS/AMI khai báo CC BY 4.0; VIVOS CC BY-NC-SA 4.0; ViMD CC BY-NC-ND 4.0; VietMed khai báo MIT; ViYT-Diar khai báo Apache-2.0. QMSum có LICENSE MIT của repository, giữ thông tin các corpus gốc. COSV và VietMed-Sum chưa xác định giấy phép phát hành lại trong phần nguồn đã kiểm tra; để `null`, không tự gán giấy phép của bộ khác. Kho này được lưu local, chưa upload/publish lại.

Tài liệu gốc bổ sung: [ViMD, EMNLP 2024](https://aclanthology.org/2024.emnlp-main.426/), [VietMed](https://arxiv.org/abs/2404.05659), [VietMed-Sum, Interspeech 2024](https://www.isca-archive.org/interspeech_2024/leduc24_interspeech.html).
