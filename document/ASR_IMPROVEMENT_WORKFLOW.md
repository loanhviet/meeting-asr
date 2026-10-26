# Chạy vòng cải thiện ASR trên development data

Quy trình dành cho họp tiếng Việt thông thường. Vòng đầu thử decoding trước
khi quyết định có cần thích nghi model. DiCoW là backend chính; PhoWhisper là
đối chứng nhận chữ trên cùng tiền xử lý và timeline người nói dự đoán.

## Môi trường và dữ liệu

App dùng `.venv`, model tác giả dùng `.cache/dicow/venv`. Cài bộ chấm CPU
riêng để không thay Transformers/Torch của tác giả:

```sh
uv venv .cache/paper-eval/venv --python .venv/bin/python
uv pip install --python .cache/paper-eval/venv/bin/python \
  -r requirements/paper-evaluation.txt
```

Kho VietMed/FLEURS dev đã được chuẩn bị theo
[hướng dẫn dữ liệu](EVALUATION_DATA_2026-10-22.md). Chuẩn bị vòng mới bằng:

```sh
.venv/bin/python scripts/prepare_asr_improvement.py --download-sources
```

Lệnh tải 4 file AMI công khai tổng 58.543.349 byte theo
[source lock](asr_improvement_sources.lock.json), xác minh số byte/SHA256 rồi
chọn dữ liệu trước inference. `--download-only` chỉ tải/kiểm tra nguồn.
Không ghi đè một `dev.jsonl` đã chọn; dùng `--out` mới cho thí nghiệm khác.

Tập vòng 1 gồm 20 VietMed pilot dev, 20 FLEURS dev và một đoạn AMI ES2011a
microphone phòng thuộc official dev. Clip tiếng Việt dài ít nhất 5 giây,
chọn bằng seed 20261026 và round-robin speaker/prompt. AMI lấy quanh phút
10–13, dịch ranh giới để tránh cắt giữa từ; thực tế là 600,000–779,340 giây.
Transcript giữ các nhóm utterance thủ công của nguồn, kiểm tra không mất/lặp
từ. Tất cả nhãn vẫn chưa được project nghe rà độc lập. AMI là tiếng Anh và
được model card nêu trong training; chỉ là kiểm tra bổ sung.

## Đóng băng, chạy và chọn cấu hình

```sh
.venv/bin/python scripts/tune_dicow_decoding.py prepare \
  --manifest data/gold/asr_improvement_v1/dev.jsonl \
  --out results/asr-improvement-round1/v1
.venv/bin/python -u scripts/tune_dicow_decoding.py run \
  --out results/asr-improvement-round1/v1
.venv/bin/python scripts/tune_dicow_decoding.py report \
  --out results/asr-improvement-round1/v1
```

`prepare` lưu manifest, checksum, cấu hình và quy tắc chọn trước khi chạy.
Chỉ nhận hàng `split=dev`, từ chối official test và đầu vào M2-only.
Grid beam 1/3/5 gồm 123 full pipeline runs; chạy tuần tự trên GPU, model
offline, không LLM/oracle. Một inference đã hoàn tất chỉ dùng lại khi
checksum audio và config hash khớp, rồi được chấm lại. Đổi cấu hình/input
thì dùng output directory mới để giữ dấu vết thí nghiệm.

Ứng viên phải hoàn thành, không lỗi, không tăng WER ở từng nguồn tiếng Việt
và không tăng AMI dev tcpWER so với beam 1. Trong các ứng viên hợp lệ, chọn
macro mean WER của hai nguồn tiếng Việt thấp nhất; hòa chọn beam nhỏ hơn.
Macro mean chỉ là mục tiêu tuning, không phải điểm chất lượng sản phẩm.
Grid chưa đủ kết quả không tạo khuyến nghị.

Lệnh `report` tạo `comparison.json` và profile
`configs/recommended-dicow-round1.yaml` nếu có ứng viên hợp lệ. Profile là
lựa chọn chạy thêm trên dev; không tự sửa `configs/default.yaml`. Đóng băng
profile trước khi chấm một test họp tiếng Việt được giữ riêng.

Sau grid, chạy đối chứng tuần tự để không làm nhiễu thời gian GPU:

```sh
.venv/bin/python scripts/compare_general_meeting_asr.py prepare \
  --out results/asr-improvement-round1/v1/beam-1
PYTHONPATH=src .cache/dicow/venv/bin/python \
  scripts/compare_general_meeting_asr.py worker \
  --out results/asr-improvement-round1/v1/beam-1
.venv/bin/python scripts/compare_general_meeting_asr.py score \
  --out results/asr-improvement-round1/v1/beam-1
```

Đối chứng dùng đúng 40 VI clip, M1 và RTTM DiariZen đã lưu. PhoWhisper có
backbone và cách conditioning khác; kết quả không cô lập riêng hiệu quả
FDDT. Thời gian control giữ ASR model resident, không so trực tiếp với
thời gian full pipeline nạp model từng file.

## Chấm theo thời gian bằng MeetEval

```sh
.venv/bin/python scripts/score_paper_metrics.py \
  path/to/reference.json path/to/transcript.json --out results/paper-score.json
```

Bộ chấm pin MeetEval 0.4.3, trả cpWER, tcpWER, tcORC-WER cùng số lỗi và số từ.
tcpWER dùng một hoán vị người nói toàn recording và chỉ cho căn chỉnh trong
collar thời gian 5 giây. tcORC-WER cho phép gán utterance tham chiếu vào các
stream dự đoán; vì vậy không phạt nhầm speaker theo cùng cách cpWER/tcpWER.
Giữ nguyên ranh giới utterance nguồn khi chấm ORC.

Chuẩn hóa theo project: chữ thường, NFC, bỏ nhóm dấu câu `.,!?;:\"'`, tách
whitespace; không dùng word segmentation tiếng Việt. Timing nội suy từ
utterance: reference `character_based`, hypothesis `character_based_points`.
Đây không phải timestamp từng từ do người gán nhãn. Hypothesis rỗng vẫn tính
toàn bộ từ reference là deletion; lỗi thời gian có thể khiến WER vượt 100%.

Định nghĩa time collar theo [DiCoW §5](https://arxiv.org/html/2501.00114v1#S5)
và thư viện [MeetEval](https://github.com/fgnt/meeteval). Có scorer đúng định
nghĩa vẫn chưa tái lập benchmark paper: dữ liệu, checkpoint, diarizer, số beam,
CTC và chuẩn hóa phải tương ứng. Paper MLC chọn checkpoint trên dev bằng
greedy, đánh giá cuối bằng beam 10; joint CTC chỉ áp dụng cho tiếng Anh trong
recipe báo cáo. Vòng 1 chỉ thử beam 1/3/5, CTC 0, diarizer đa miền.
Xem [MLC-SLM §3](https://arxiv.org/html/2506.13414v1#S3).

## Kiểm tra API LLM đang cấu hình

```sh
# Chỉ kiểm tra đủ cấu hình, không gọi mạng.
.venv/bin/meeting-asr llm-check
# Gửi đúng một prompt tĩnh ngắn, không gửi transcript người dùng.
.venv/bin/meeting-asr llm-check --probe \
  --out results/asr-improvement-round1/v1/llm-probe.json
```

Probe giới hạn 512 output tokens, timeout tối đa 20 giây, không retry. Báo cáo
phân biệt `configuration_ready`, `api_accessible`, `ready`, HTTP status và
provider code; không lưu key, URL endpoint, body lỗi hoặc transcript.
`ready=true` cần phản hồi JSON đúng canary, chưa chứng minh chất lượng biên
bản/hỏi đáp. Lỗi quota cần xử lý ở tài khoản cung cấp credential.

Sau khi có đủ grid, controls và probe, xuất bằng chứng gọn để review qua Git:

```sh
.venv/bin/python scripts/report_asr_improvement.py \
  --out results/asr-improvement-round1/v1 \
  --evidence document/ASR_IMPROVEMENT_ROUND1_2026-10-26.json
```

Script kiểm tra cùng audio, phiên bản model/runtime, beam thực sự, oracle
tắt, đủ control và mẫu số chấm. Artifact chi tiết cùng audio/cache vẫn local
trong `data/`, `results/`, `.cache/`.
