# Vòng cải thiện 1 cho họp tiếng Việt thông thường

Hoàn tất ngày 26/10/2026 trên branch `feat/asr-quality-improvement`:
**123 full pipeline DiCoW + 40 đối chứng PhoWhisper**, không có inference
thất bại. Chạy hoàn tất không đồng nghĩa transcript đúng.

## Kết luận

Beam 3 là ứng viên để thử tiếp trên dev, nhưng lợi ích nhận chữ tiếng Việt
trong lượt này rất nhỏ. Giữ beam 1 làm mặc định. Chưa có bằng chứng để gọi
hệ thống là đã nghiệm thu cho các cuộc họp tiếng Việt thông thường, và chưa
chạy fine-tune. Hướng tiếp theo là bộ họp đại diện có nhãn đã nghe rà và đánh
giá đối chứng trên họp đầy đủ.

LLM hiện bị chặn bởi quota: canary thật nhận HTTP **403**, provider code
**`insufficient_quota`**. Đã bổ sung công cụ chẩn đoán; cần quota/credential
còn hiệu lực để tiếp tục chấm chất lượng biên bản và hỏi đáp qua API này.

## Dữ liệu và cách chọn

Tập dev được đóng băng trước suy luận:

| Nguồn | Số mẫu | Thời lượng | Phạm vi |
|---|---:|---:|---|
| VietMed pilot dev | 20 | 125,00 giây | 18 speaker ID, 9 recording; nội dung y tế |
| FLEURS VI dev | 20 | 256,50 giây | 20 prompt; lời đọc, không có speaker ID để xác nhận tách người nói |
| AMI ES2011a dev | 1 | 179,34 giây | Microphone phòng, 4 người, 550 từ tham chiếu; tiếng Anh |
| Tổng | 41 | 560,84 giây | Không gộp thành một điểm chất lượng sản phẩm |

Chọn seed 20261026, clip tối thiểu 5 giây, round-robin theo speaker/prompt.
AMI thuộc official dev, lấy 600,000–779,340 giây từ Array1-01; ranh giới
tránh cắt giữa từ. Tải thêm 58.543.349 byte từ nguồn công khai, dưới giới
hạn 2 GB. [Source lock](asr_improvement_sources.lock.json) giữ URL và SHA256.

Các nhãn là tham chiếu do nguồn công bố, chưa được project nghe rà độc lập.
AMI là tiếng Anh và được model card nêu trong training, nên chỉ kiểm tra bổ
sung. Không dùng lại các test đã xem trong
[lượt đánh giá trước](GENERAL_MEETING_EVALUATION_2026-10-26.md) để chọn beam.
Đoạn AMI cũ chỉ dùng kiểm tra chéo scorer: MeetEval cpWER 25,326% khớp bộ
chấm cpWER cũ; tcpWER của chính đoạn đó là 27,937%, cho thấy hai thước đo
không thể thay thế nhau.

## Kết quả DiCoW

| Beam | WER FLEURS dev | WER VietMed dev | Macro mean để chọn | Thời gian pipeline 41 mẫu | Peak allocated VRAM | Hợp lệ |
|---|---:|---:|---:|---:|---:|---|
| 1 | 14,49% (99/683) | 23,49% (113/481) | 18,99% | 445,09 giây | 1,99 GiB | Có, mặc định hiện tại |
| 3 | 14,49% (99/683) | 23,28% (112/481) | 18,89% | 450,47 giây | 2,37 GiB | Có, ứng viên dev |
| 5 | 14,20% (97/683) | 23,70% (114/481) | 18,95% | 471,72 giây | 2,90 GiB | Không |

Quy tắc đã ghi trước khi chạy: hoàn tất, không lỗi, không tăng WER ở từng
nguồn tiếng Việt và không tăng AMI tcpWER so với beam 1; sau đó tối thiểu hóa
macro mean WER của hai nguồn tiếng Việt, hòa chọn beam nhỏ hơn. AMI không
tham gia mục tiêu WER tiếng Việt. Beam 5 bị loại vì VietMed tăng từ 113 lên
114 lỗi; beam 3 giảm còn 112 lỗi, FLEURS vẫn 99 lỗi trên 683 đơn vị tham chiếu.

Lợi ích beam 3 rất nhỏ: VietMed tốt hơn ở 3 clip, tệ hơn ở 3, hòa ở 14;
FLEURS tốt hơn ở 2, tệ hơn ở 1, hòa ở 17. Tổng hai bộ giảm đúng **một lỗi**
trên 1.164 đơn vị tham chiếu. Macro mean giảm khoảng **0,104 điểm phần trăm**;
đây không phải một cải thiện lớn đã được xác lập trên họp thật. CER của cả
hai bộ còn tăng nhẹ khi đổi beam 1 sang 3.

Mỗi lượt chạy nạp model riêng; thời gian bảng lấy từ pipeline `run.json`,
không gồm scorer. Đây là một lượt đo mỗi mẫu/cấu hình, chưa phải benchmark
latency lặp. Peak VRAM là bộ nhớ **PyTorch allocated**, không phải toàn bộ
VRAM thiết bị. GPU thực tế là RTX 3050 Laptop 4 GB, FP16, target speaker
decode tuần tự; CTC weight 0. Không thay checkpoint hoặc diarizer.

| Beam | AMI WER theo thứ tự thời gian | cpWER | tcpWER, collar 5 giây | tcORC-WER, collar 5 giây |
|---|---:|---:|---:|---:|
| 1 | 25,82% | 22,36% | 24,00% | 20,91% |
| 3 | 24,00% | 20,55% | 22,55% | 18,73% |
| 5 | **185,82%** | **182,55%** | **184,55%** | **180,55%** |

Beam 5 phát sinh lặp text rất dài: 1.414 đơn vị dự đoán so với 550 đơn vị
tham chiếu, **925 insertion**; 5-gram `bit of a bit of` xuất hiện 288 lần
trong transcript. Đây là bằng chứng lặp ở output, chưa phải kết luận sau
nghe độc lập. WER vượt 100% là hợp lệ khi số lỗi insertion lớn. Không bỏ
mẫu này khỏi mẫu số hoặc tự cắt text rồi báo điểm đẹp hơn. Beam 3 không
gặp dạng lặp dài này trên đoạn AMI đã chọn; chưa bảo đảm mọi họp đều tránh được.

RTTM dự đoán **khớp nguyên byte trên cả 41 mẫu giữa ba beam**. Vì vậy khác
biệt ở đây đến từ decoding với timeline giữ nguyên, không phải lượt chạy
diarization khác nhau.

Trên đoạn AMI dev, DER giữ nguyên ở các beam: **12,67% strict** (collar 0,
giữ overlap), **8,13% relaxed** (collar 0,25 giây, bỏ overlap). Đây là các
điểm của ES2011a, không phải mức cải thiện so với đoạn ES2004a cũ.

## Đối chứng PhoWhisper

| Nguồn dev | DiCoW beam 1 | DiCoW beam 3 | PhoWhisper-medium |
|---|---:|---:|---:|
| FLEURS VI, 20 clip | 14,49% | 14,49% | **14,20%** (97/683) |
| VietMed, 20 clip | 23,49% | **23,28%** | 26,40% (127/481) |

Trên dev mới, PhoWhisper nhỉnh hơn 2 lỗi ở FLEURS so với beam 1 nhưng kém
hơn 14 lỗi ở VietMed. Vì vậy **không tự chuyển mọi clip ngắn sang PhoWhisper**.
Ưu thế PhoWhisper trong các subset test chẩn đoán cũ không tự bảo đảm ưu thế
trên mọi miền/dữ liệu mới.

Đối chứng dùng đúng 40 clip tiếng Việt, M1 và RTTM DiariZen dự đoán đã lưu
của beam 1; không có oracle/LLM. PhoWhisper-medium khác backbone và cách
conditioning, nên không diễn giải thành ablation riêng FDDT. Model control
giữ resident và bỏ qua chạy lại M1/M2, vì vậy không so thời gian control với
full pipeline DiCoW. Clip ngắn chưa chứng minh chất lượng trên cuộc họp
nhiều người, microphone phòng và overlap.

## Scorer có giống paper không?

Đã thêm **MeetEval 0.4.3** trong môi trường CPU riêng, chấm cpWER, tcpWER và
tcORC-WER; hai thước đo có thời gian dùng collar **5 giây**. Giữ ranh giới
utterance tham chiếu cho ORC, cho phép hypothesis rỗng để tính đủ deletion.
Kiểm thử bao gồm hoán vị speaker, gộp stream, sai thời gian và đầu ra rỗng.

Định nghĩa temporal metric theo [DiCoW §5](https://arxiv.org/html/2501.00114v1#S5)
và [MeetEval](https://github.com/fgnt/meeteval). **Chưa tái lập benchmark paper**:
đang dùng tập dev nhỏ khác miền, checkpoint MLC và diarizer đa miền; thử
beam 1/3/5 thay vì cấu hình cuối beam 10 của
[MLC-SLM §3](https://arxiv.org/html/2506.13414v1#S3). CTC vẫn bằng 0.

Chuẩn hóa theo project: chữ thường, bỏ nhóm dấu câu cố định, NFC và tách
whitespace; tiếng Việt không dùng word segmentation. Mốc từ được nội suy
từ utterance bằng `character_based` cho reference và
`character_based_points` cho hypothesis. Không gọi đây là timestamp từng từ
đã được người gán nhãn hoặc so trực tiếp số này với bảng paper khác protocol.

## Phần mềm đã hoàn tất

- Scorer CLI, môi trường pin riêng, và bước cài scorer trong CI.
- Chuẩn bị dữ liệu có checksum, xác nhận official dev, giữ utterance AMI.
- Grid khóa input/config/rule; resume chỉ dùng lại inference khớp audio và
  config, sau đó chấm lại. Nhãn tham chiếu ở scorer, không vào worker.
- Profile [recommended-dicow-round1.yaml](../configs/recommended-dicow-round1.yaml)
  chọn beam 3 để thử tiếp; `configs/default.yaml` giữ beam 1.
- `llm-check --probe` gửi một prompt tĩnh, tối đa 512 output tokens, timeout
  20 giây, không retry, không gửi transcript người dùng. Chỉ dùng **một**
  request thật trong vòng này. Báo cáo không lưu key/body lỗi/URL endpoint.

Kiểm chứng: **169 tests đạt, 3 skip** do thiếu dependency inference tùy chọn
trong app venv; Ruff check/format đạt, build wheel/sdist đạt. Không thay
Torch/Transformers trong author runtime. Chi tiết số liệu và số lỗi từng
clip nằm trong [evidence JSON](ASR_IMPROVEMENT_ROUND1_2026-10-26.json);
artifact đầy đủ tại `results/asr-improvement-round1/v1/` trên máy hiện tại.
Lệnh tái chạy ở [workflow](ASR_IMPROVEMENT_WORKFLOW.md).

Chạy thử profile beam 3, giữ LLM tắt khi đánh giá nhận dạng:

```sh
MEETING_LLM_ENABLED=false .venv/bin/meeting-asr run path/to/meeting.wav \
  --config configs/recommended-dicow-round1.yaml --out results/beam3-try
```

## Việc tiếp theo phù hợp bài toán

1. Chuẩn bị khoảng **8 cuộc họp tiếng Việt, 6–10 phút/cuộc** thuộc nhiều chủ
   đề thông thường, người nói/vùng giọng, microphone và mức overlap. Chia
   4 dev/4 test theo cuộc họp gốc trước tuning, ưu tiên tách người nói. Một
   người chép, một người rà đoạn khó, số/tên/phủ định/quyết định/thời hạn.
   Giữ test riêng; không dùng chính bộ nghiệm thu làm train.
2. Nghe rà ba ViYT đã đánh dấu trước khi sửa nhãn hoặc điều chỉnh speech/
   clustering. Việc này vẫn chờ kiểm chứng bằng nghe; không dùng đồng thuận
   của hai model để tự chứng nhận gold.
3. Trên bộ họp đó, so DiCoW beam 1/3 và PhoWhisper theo recording, WER,
   tcpWER/DER và công nghe sửa. Beam 3 chỉ là ứng viên; chỉ đổi mặc định khi
   có lợi đủ rõ và không làm tăng lỗi quan trọng. Đưa lỗi lặp AMI vào tập
   kiểm tra hồi quy; chấm cơ chế phát hiện/cảnh báo lặp trước khi mở rộng
   beam, không mặc định beam lớn hơn sẽ tốt hơn.
4. Cấp quota/credential hợp lệ cho provider hiện tại, chạy lại canary rồi
   chấm biên bản/hỏi đáp trên transcript chuẩn và ASR riêng. Lỗi API chưa
   cho phép kết luận chất lượng semantic của hệ thống.
5. Chỉ mở pilot fine-tune khi có lỗi lặp đã xác định và **train riêng** với
   nhãn phù hợp recipe tác giả. Chạy smoke training kiểm tra loss/VRAM/
   checkpoint trước; khả năng inference trên GPU 4 GB chưa chứng minh đủ
   bộ nhớ training. Không cần chuyển sang fine-tune chỉ vì tăng beam ít tác dụng.

Mục tiêu gần nhất là giảm công nghe sửa và bảo toàn quyết định/ai làm gì,
không phải chỉ hạ một điểm WER trên clip lời đọc/y tế. Họp IT là một nhóm
tình huống bổ sung trong bộ nghiệm thu.
