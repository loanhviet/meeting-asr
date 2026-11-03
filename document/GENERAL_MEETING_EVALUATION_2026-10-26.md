# Đánh giá hệ thống cho cuộc họp thông thường — 26/10/2026

**Đã hoàn tất lượt đo:** 143 đầu vào qua pipeline đầy đủ, 100 file qua bước
diarization và 130 đối chứng PhoWhisper. Không có lượt inference thất bại.
Đây là bằng chứng chạy thật và điểm nền chẩn đoán; bộ nghiệm thu cuộc họp
tiếng Việt nhiều người vẫn cần bổ sung.

Mục tiêu của dự án là các cuộc họp tiếng Việt thông thường. IT chỉ là một
nhóm tình huống. Lượt đo này chủ động dùng lời đọc phổ thông, giọng vùng miền,
hội thoại tự nhiên, hội thoại nhiều người và microphone phòng để kiểm tra
từng phần của hệ thống.

## Dữ liệu và cách chọn

Tận dụng kho đã tải ngày 22/10; tải thêm audio microphone phòng AMI ES2004a
Array1-01 từ nguồn chính thức: **33.579.394 byte**, SHA256
`6936edac5d0904fc5c4ab175546c5cc5366601fdc1b1e5183a6ea2c10f05d150`.
Trích cùng đoạn 301,200–480,305 giây với mẫu headset có sẵn, đúng sample count.

| Nguồn | Phần thực sự chấm | Nhãn và vai trò |
|---|---|---|
| [ViYT-Diar](https://huggingface.co/datasets/tuanduy1612/ViYT-Diar) | Toàn bộ 100 file, 104,32 phút | Nhãn speaker/timestamp thủ công theo tác giả; chấm M2. Có 10 file chạy thêm toàn pipeline để kiểm tra tương đương. Không có transcript chuẩn. |
| [FLEURS VI](https://huggingface.co/datasets/google/fleurs) | 40 prompt test khác nhau, 8,26 phút | Kiểm tra nhận chữ phổ thông/lời đọc. Metadata giới tính nguồn trong mẫu chỉ có MALE; không suy ra đã cân bằng người nói. |
| [ViMD](https://aclanthology.org/2024.emnlp-main.426/) | 63 clip test, 20,43 phút | Một clip/mã tỉnh theo danh mục nguồn, đủ 63 mã. Đánh giá nhận chữ theo vùng; không phải toàn bộ official test. |
| [VietMed](https://huggingface.co/datasets/leduckhai/VietMed) | 27 clip pilot test, 2,80 phút | Một clip/người nói đủ điều kiện. Là tiếng nói miền y tế, bổ sung kiểm tra độ bền, không đại diện họp thông thường. |
| [COSV](https://cosv.ortolang.fr/le-corpus/) Đức–Ly | Cả bản ghi 46,86 phút | Hội thoại phỏng vấn tự nhiên, transcript thủ công nguồn. Chấm text toàn bản ghi; thiếu timestamp/nhãn người nói đủ tin cậy để chấm DER/cpWER. |
| [AMI](https://groups.inf.ed.ac.uk/ami/download/) ES2004a | Hai bản thu của cùng đoạn 2,99 phút | Họp bốn người, manual words và RTTM/UEM. So microphone headset/phòng; báo riêng tiếng Anh. |
| [QMSum](https://github.com/Yale-LILY/QMSum) | 35 cuộc họp validation, 237 câu hỏi cụ thể | Chấm tìm nguồn theo evidence spans. Chỉ text tiếng Anh; không chấm ASR hay độ đúng câu trả lời. |

Selection được chốt trước khi xem dự đoán: seed `20261026`, thứ tự hash ID,
chỉ chọn file dài ít nhất 5 giây; không lọc theo lỗi ASR. Pipeline đầy đủ có
**94,78 phút audio**. Trong 100 file diarization có 10 file trùng với phần
pipeline, và hai bản AMI là cùng nội dung qua hai microphone. Không cộng các
lượt chạy thành số cuộc họp độc lập.

Các nhãn là tham chiếu do nguồn công bố, chưa được nhóm nghe rà độc lập.
VietSuperSpeech được tìm thấy trong khảo sát nhưng sử dụng pseudo-label ASR
theo [bài báo của tác giả](https://arxiv.org/abs/2603.01894); không dùng nó làm
gold chấm điểm trong lượt này.

## Cấu hình và kiểm tra tính hợp lệ

- Hệ đang dùng: DiariZen + `BUT-FIT/DiCoW_v3_MLC`, CUDA/FP16, beam 1,
  `ctc_weight=0`, seed suy luận 42, target decode tuần tự.
- Cấu hình và revision model giữ theo project; không tuning bằng kết quả này.
  Ba file production `pipeline.py`, `dicow_runner.py`, `preprocess.py` khớp
  hash lúc chốt selection.
- Cả 143 lượt có checksum input khớp, inference cache miss, LLM tắt và không
  dùng oracle RTTM. Reference chỉ dùng ở tiến trình chấm.
- M2 riêng dùng cùng tiền xử lý, code/model đã pin và batch size của ứng dụng.
  Cả 10 mẫu đối chiếu có phân hoạch speaker và biên RTTM trùng với pipeline
  đầy đủ, cho phép hoán vị tên speaker.
- WER dùng normalization hiện có và tách bằng khoảng trắng, gần đơn vị âm
  tiết tiếng Việt. CER bỏ space nhưng giữ dấu. Cộng edit counts theo clip;
  không nối alignment qua ranh giới các clip.
- DER dùng UEM của mẫu; chấm bốn tổ hợp collar/overlap. Không sửa RTTM dự đoán.
  Mốc model vượt mép audio do padding được giới hạn bởi UEM khi chấm.
- Với COSV MP3, thời lượng container là 2811,492 s, audio giải mã là
  2811,4024375 s. Xác nhận đúng cả file bằng SHA256; không ép timestamp gold
  từ thời lượng danh nghĩa. Các mẫu có nhãn timeline vẫn kiểm tra thời lượng.

## Nhận chữ tiếng Việt

### Phạm vi so với paper DiCoW

Lượt này là đánh giá chẩn đoán ứng dụng, **chưa phải tái lập benchmark paper**.
Luồng inference dùng code/checkpoint tác giả và cùng nguyên lý
DiariZen → STNO → DiCoW/FDDT trên audio đầy đủ. Cần phân biệt paper DiCoW gốc
với paper MLC-SLM gắn với checkpoint `DiCoW_v3_MLC` đang dùng.

| Thành phần | Lượt đo hiện tại | Thiết lập công bố cần đối chiếu |
|---|---|---|
| Dữ liệu | Các subset tiếng Việt, COSV và một đoạn AMI | DiCoW gốc có các split AMI, NOTSOFAR-1, Libri2Mix, LibriCSS; bản MLC dùng MLC-SLM |
| Lỗi transcript nhiều người | WER/CER là chính; cpWER chỉ ở AMI có nhãn phù hợp | DiCoW gốc có cpWER, tcpWER, ORC-WER, tcORC-WER |
| Ràng buộc thời gian khi chấm chữ | Chưa triển khai tcpWER/tcORC-WER | DiCoW gốc dùng collar 5 s cho thước đo có ràng buộc thời gian |
| DER | Báo collar 0 và 0,25 s, giữ/bỏ overlap; UEM từng mẫu | Hai paper công bố DER với collar 0; còn cần khớp dataset/annotation/overlap policy |
| Decoding | Beam 1; CTC weight 0 | MLC chọn checkpoint bằng greedy trên dev; đầu ra test cuối beam 10, joint CTC 0,2 cho tiếng Anh |
| Model | ASR MLC pretrained + diarizer multi-domain `s80-md` | MLC có DiariZen fine-tune theo challenge hai người; không phải đúng diarizer đang dùng |
| Đối chứng | PhoWhisper trên cùng DiariZen dự đoán | Không tái lập đầy đủ baseline/ablation của tác giả; khác backbone và cách conditioning |

Nguồn: [DiCoW gốc, §5.1–5.2](https://arxiv.org/html/2501.00114v1#S5) và
[BUT MLC-SLM, §3–4](https://arxiv.org/html/2506.13414v1#S3).
Collar 5 s của tcpWER là dung sai ghép từ theo thời gian, khác collar DER.
Không lấy WER 14,94% trên FLEURS để so trực tiếp với tcpWER tiếng Việt 24,7%
trên MLC development. Các điểm biên bản/QA/confidence là đánh giá riêng của
ứng dụng, không thay thước đo speaker-attributed ASR của paper.

Để tiến gần protocol paper: dùng cùng split và loại microphone, chuẩn hóa
text theo benchmark, bổ sung scorer tcpWER/tcORC-WER chính thức, ghi đầy đủ
collar/overlap policy, chạy cả GT diarization và diarization dự đoán. Phần
nghiệm thu họp tiếng Việt thông thường cần một nhánh đánh giá độc lập theo
các điều kiện sản phẩm thực sự phục vụ.

### Điểm trên các tập nhận chữ

| Tập | Clip | Reference units | WER | CER |
|---|---:|---:|---:|---:|
| FLEURS VI test subset | 40 | 1.131 | 14,94% | 8,82% |
| ViMD diagnostic subset | 63 | 4.159 | 20,82% | 12,07% |
| VietMed pilot test subset | 27 | 616 | 24,19% | 17,68% |
| COSV Đức–Ly full | 1 | 11.574 | 29,17% | 21,91% |

Không có một điểm WER chung cho bốn miền. COSV là phép chấm thăm dò toàn
transcript: cách ghi từ đệm, số, lượt chồng tiếng và phần đầu/cuối cần nghe
rà. Chênh lệch text ở những phần đó chưa chứng minh hallucination của model
hoặc lỗi nhãn nguồn nếu chưa kiểm tra âm thanh.

ViMD theo nhóm vùng nguồn: Bắc **17,58%** trên 25 clip, Trung **29,25%** trên
19 clip, Nam **16,84%** trên 19 clip. Mẫu ít và khác độ khó nội dung/điều kiện
thu; đây là dấu hiệu cần kiểm tra thêm, chưa chứng minh giọng vùng là nguyên
nhân duy nhất. Có 1/40 clip FLEURS, 1/63 ViMD và 6/27 VietMed được dự đoán hơn
một người nói; đây là thống kê output, không thay nhãn diarization chuẩn.

## Phân người nói tiếng Việt

**Kết quả chính giữ đủ 100 file ViYT-Diar:**

| Quy ước | DER | Miss | False alarm | Confusion |
|---|---:|---:|---:|---:|
| Collar 0, giữ overlap | 14,07% | 1,27% | 10,66% | 2,14% |
| Collar 0,25 s, bỏ overlap | 7,83% | 0,65% | 5,12% | 2,07% |
| Collar 0, bỏ overlap | 14,02% | — | — | — |
| Collar 0,25 s, giữ overlap | 7,93% | — | — | — |

Thành phần lỗi tính theo mẫu số speaker-time của từng quy ước. Chênh lệch
strict/relaxed ở đây chủ yếu liên quan dung sai biên, không thể quy toàn bộ
cho việc xử lý overlap. Đúng số nhãn người nói ở **85/100 file**; 13 file
dự đoán thừa và 2 file thiếu so với nhãn nguồn.

Bootstrap 2.000 lượt theo recording, giữ trọng số speech-time: khoảng 95%
cho strict DER là **11,23–17,83%**, relaxed DER **4,94–11,71%**. Giả định các
recording là đơn vị lấy mẫu; không bảo đảm độc lập với dữ liệu huấn luyện.

Có một vấn đề tham chiếu cần kiểm tra: `C4HFERLpRfI`, `Uaq5N3FbQb4`,
`ed0Vt0NxJUI` chỉ có nhãn `Speaker_2` ở phần muộn của audio. Tổng speech được
gán nhãn lần lượt khoảng 4,34 / 11,21 / 19,67 giây trong file khoảng một
phút. Đã kiểm tra trực tiếp parquet gốc: label và timestamp khớp bản RTTM
xuất ra, không phải converter làm mất người nói. **Chưa nghe rà để kết luận
nhãn thiếu hay model phát hiện thừa speech.**

Phân tầng theo số speaker tham chiếu, không thay điểm chính:

| Nhãn nguồn | File | Strict DER | Relaxed DER |
|---|---:|---:|---:|
| Một speaker label | 3 | 329,09% | 396,57% |
| Hai speaker labels | 97 | 11,84% | 5,32% |

DER có thể vượt 100% khi false alarm lớn hơn tổng speaker-time tham chiếu.
Ba file vẫn được giữ trong kết quả 100 file. ViYT còn có giới hạn miền:
97 file có hai nhãn speaker, 3 file có một nhãn; 33 file có overlap tham chiếu, tỷ lệ
overlap trung bình theo file 0,66%, cao nhất 7,96%. Cần dữ liệu tiếng Việt
3–6 người và chồng tiếng rõ để nghiệm thu phạm vi cuộc họp.

## Microphone phòng: AMI bổ sung

| Audio cùng nội dung | WER | cpWER | Strict DER | Relaxed DER | Speaker dự đoán/chuẩn |
|---|---:|---:|---:|---:|---:|
| Headset mix | 24,54% | 25,33% | 36,44% | 24,66% | 4/4 |
| Array1-01 microphone phòng | 39,69% | 42,82% | 27,04% | 17,49% | 4/4 |

Trên đoạn này, microphone phòng làm nhận chữ khó hơn, trong khi DER lại thấp
hơn. Hai stage cần được phân tích riêng. AMI là tiếng Anh, đoạn ngắn, và được
[model card DiCoW](https://huggingface.co/BUT-FIT/DiCoW_v3_MLC) nêu trong dữ liệu
huấn luyện; không coi đây là điểm tổng quát tiếng Việt hoặc benchmark AMI đầy đủ.

## Đối chứng nhận chữ trên cùng DiariZen

Giữ lại waveform sau M1 và RTTM **dự đoán** của từng clip; dùng decoder
PhoWhisper của project trên các audio cuts. Cả 130 đối chứng thành công.
Model `vinai/PhoWhisper-medium` dùng snapshot local đã pin
`55a7e3eb6c906de891f8f06a107754427dd3be79`; không có đáp án trong worker input.

| Tập giống hệt nhau | DiCoW WER | DiariZen + PhoWhisper WER |
|---|---:|---:|
| FLEURS, 40 clip | 14,94% | 12,56% |
| ViMD, 63 clip | 20,82% | 16,54% |
| VietMed, 27 clip | 24,19% | 23,05% |

Đây là bằng chứng nên tiếp tục kiểm tra phần nhận chữ. Hai hệ khác backbone
và cách conditioning/cắt audio; không cô lập FDDT. Các clip ngắn này không
chứng minh PhoWhisper tốt hơn cho họp nhiều người nói chồng. CER VietMed của
PhoWhisper là 17,98%, cao hơn DiCoW 17,68%; cải thiện WER không đồng nghĩa
mọi thước đo cùng tốt lên. Cấu hình production vẫn được đo theo DiCoW hiện tại.

## Biên bản và hỏi đáp

Canary thật với cấu hình biên bản `qwen3.7-max` trả **HTTP 403**. Không có
điểm semantic cho summary/Q&A trong lượt này. Canary không thay provider/model;
thí nghiệm Kimi hiệu chỉnh ngày 22/10 là một lượt khác, không áp điểm cải thiện
của tập dev đó lên các tập test mới.

Chẩn đoán retrieval bằng đúng hàm production trên QMSum validation:

| Cấu hình | Câu trúng ít nhất một vùng nguồn | Tỷ lệ | Text context trung bình |
|---|---:|---:|---:|
| top_k=6, cap 12.000 | 173/237 | 73,00% | 3.006 ký tự |
| top_k=12, cap 12.000 | 200/237 | 84,39% | 4.597 ký tự |
| top_k=12, cap 24.000 | 201/237 | 84,81% | 5.848 ký tự |

Evidence spans có thể rộng; một lượt trúng span không chứng minh đủ thông tin
hoặc trả lời đúng. Ba cấu hình dùng cùng 237 câu, không phải 711 câu độc lập.
Không có câu không trả lời được trong phần specific queries này. Đây là hướng
thử trên dev tiếng Việt trước khi thay retrieval của ứng dụng.

## Vận hành và việc nên ưu tiên

143 pipeline chạy nối tiếp trên RTX 3050 Laptop 4 GB: tổng thời gian M1–M5
theo `run.json` khoảng **39,03 phút** cho 94,78 phút audio, gồm nạp runtime/model
mỗi file, không gồm CLI startup. COSV riêng mất **607,27 giây**. M2 và nhánh
PhoWhisper sau đó chạy model resident và có thời gian dùng GPU đồng thời;
không dùng timing của chúng để kết luận thông lượng hoặc SLA.

**Thứ tự phù hợp:**

1. Nghe rà ba tham chiếu ViYT đã đánh dấu; chuẩn bị bộ nghiệm thu tiếng Việt
   gồm nhiều loại cuộc họp, 2–6 người, microphone phòng và overlap; tách dev/test.
2. So các nhánh nhận chữ và decoding trên dev đó. Giữ DiCoW làm hướng nghiên
   cứu chính, dùng đối chứng để xác định điều kiện mạnh/yếu và tín hiệu cần soát.
3. Khôi phục quyền truy cập LLM; chấm biên bản/QA với transcript chuẩn và ASR
   riêng, kiểm tra quyết định, owner/deadline và dẫn chứng. Thử retrieval trên
   bộ hỏi đáp tiếng Việt có cả câu thiếu bằng chứng.
4. Hiệu chỉnh confidence và đo tiết kiệm công review; sau đó tích hợp gợi ý
   Kimi có chấp nhận/từ chối vào web. Fine-tune được cân nhắc sau khi có đủ
   dữ liệu và phân loại lỗi lặp có hệ thống.

Đầu ra và tiêu chí từng mốc ở
[kế hoạch chi tiết](GENERAL_MEETING_PLAN_2026-10-26.md).

## Artifact và tái chạy

Gốc artifact: `results/general-meetings-20261026/v1/`.

![Tổng quan chất lượng theo từng tập và tác vụ](../results/general-meetings-20261026/v1/quality-overview.png)

![Đối chứng nhận chữ trên cùng DiariZen](../results/general-meetings-20261026/v1/asr-control-comparison.png)

- `selection.json`, `config.yaml`: lựa chọn trước dự đoán, checksum, config, code/model pins.
- `summary.json`, `scores.jsonl`, `diagnostics.json`: điểm, mẫu số và phân tích.
- `review.csv`: danh sách nghe rà nhận chữ, trạng thái pending; không tự nâng nhãn máy thành gold.
- `viyt_original_annotation_audit.json`: đối chiếu ba hàng parquet gốc với RTTM.
- `phowhisper_comparison_summary.json`, `phowhisper_comparison_rows.jsonl`: đối chứng ghép cặp.
- `qmsum_retrieval_summary.json`, `qmsum_retrieval_rows.jsonl`, `llm-canary.json`: downstream.
- `quality-overview.png/.svg`, `asr-control-comparison.png/.svg`: biểu đồ.
- `pipeline/`, `diarization/`, `phowhisper-control/`: dự đoán gốc và provenance từng mẫu.
- `software_validation.json`, `software-tests.txt`: **147 passed, 3 skipped**;
  Ruff check/format đạt, có regression tests cho UEM, inference lỗi, hash và
  thời lượng giải mã. Tests phần mềm không thay điểm chất lượng phía trên.

Tổng hợp/tạo lại báo cáo từ artifact đã lưu, không gọi model/API:

```sh
.venv/bin/python scripts/evaluate_general_meetings.py collect \
  --out results/general-meetings-20261026/v1
.venv/bin/python scripts/compare_general_meeting_asr.py score \
  --out results/general-meetings-20261026/v1
.venv/bin/python scripts/report_general_meeting_evaluation.py \
  --out results/general-meetings-20261026/v1
```

Tạo lượt inference mới bằng thư mục output mới qua `prepare`, `run`,
`prepare-diarization`, `run-diarization`, `collect` của script evaluation.
`prepare_general_meeting_sources.py` kiểm checksum audio AMI; hướng dẫn dựng
kho còn lại ở [EVALUATION_DATA_2026-10-22.md](EVALUATION_DATA_2026-10-22.md).
