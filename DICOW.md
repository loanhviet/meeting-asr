# Thử DiariZen + DiCoW theo tác giả

Branch: `feat/dicow-author-pipeline`. Baseline Pyannote/ECAPA + PhoWhisper vẫn chạy bằng cấu hình cũ. Profile mới dùng checkpoint DiCoW đa ngôn ngữ MLC đã được tác giả fine-tune, không tái huấn luyện paper v1.

## Kiến trúc đang tích hợp

Audio mono 16 kHz → **DiariZen** của tác giả → nhãn hoạt động theo người nói → **STNO** (Silence, Target, Non-target, Overlap) → **DiCoW với FDDT đã huấn luyện** → text và timestamp được model sinh cho mỗi target speaker → lượt nói/confidence/SQLite/website của project.

Adapter dùng trực tiếp `DiCoWPipeline.preprocess`, `_forward` và `postprocess_text` từ checkout tác giả đã cố định. ASR nhận audio dài cùng STNO; không đưa các đoạn diarization riêng lẻ vào PhoWhisper. DiariZen được giải phóng trước khi nạp DiCoW; target được decode tuần tự để giảm VRAM. Đây là điều chỉnh cách lập lịch suy luận, không thay FDDT hay trọng số của tác giả.

Nguồn:

- [Inference repo](https://github.com/BUTSpeechFIT/DiCoW), commit `801e2130d00142a7da5845754f87b97550053a75`.
- DiariZen submodule của repo đó: `4d1009d4a3f1bc41777623e9d74b8081564cddf9`, bao gồm fork Pyannote của tác giả.
- [DiCoW_v3_MLC](https://huggingface.co/BUT-FIT/DiCoW_v3_MLC), revision `99c64e8dc409a158816e808a1ee556cdfd0af51c`.
- [DiariZen đa miền](https://huggingface.co/BUT-FIT/diarizen-wavlm-large-s80-md), revision `6285693ddd5b38e8229acb93f864f3d04a82bee1`. Dùng bản đa miền thay bản MLC chuyên dữ liệu hai người để thử nguồn 3–4 người của project.
- Embedding WeSpeaker: revision `837717ddb9ff5507820346191109dc79c958d614`.

## Cài và chạy

```bash
python scripts/setup_dicow.py
MEETING_LLM_ENABLED=false uv run --no-sync meeting-asr run data/real/haveasip_13_giang_oi/sample_5min.wav --config configs/dicow-author.yaml --out results/dicow-author/haveasip_13
```

Môi trường tác giả nằm ở `.cache/dicow/venv`, không thay `.venv` baseline. Runtime cố định Transformers 4.42.4 vì custom code của checkpoint MLC còn dùng `WHISPER_ATTENTION_CLASSES`; API này đã bị bỏ ở bản 4.55 của repo inference hiện tại. Torch/Torchaudio 2.8 và scoped metadata allowlist giữ weights-only loading; không vô hiệu hóa loader toàn process. Cài fork Pyannote cần build constraint `setuptools<81` vì setup cũ còn dùng `pkg_resources`.

`setup_dicow.py` lưu phiên bản package trong `.cache/dicow/runtime.json`. Cache joint M2/M3 phụ thuộc checksum audio, model revisions, cấu hình, upstream commit và manifest runtime. `--no-cache` bỏ cache inference nhưng vẫn dùng trọng số đã tải.

Để xem trên website:

```bash
MEETING_LLM_ENABLED=false uv run --no-sync meeting-asr serve --config configs/dicow-author.yaml
# Terminal khác: cd web && NEXT_PUBLIC_API_URL='' npm run dev
```

API dùng result store hiện có; bản upload mới chạy theo profile của server. Job cũ giữ kết quả và bản sửa của nó. LLM tắt trong thí nghiệm ASR này. Credentials vẫn đọc từ `.env` hoặc môi trường, không ghi vào artifact.

## Artifact và so sánh

Mỗi output giữ `diarization.rttm` gốc để chấm DER; `transcript.json` dùng timestamp do DiCoW sinh. `dicow-author-output.json` giữ chuỗi gốc theo target, `dicow-provenance.json` giữ revisions, device, dtype, lịch decode, thời gian và peak CUDA allocated theo stage. Peak allocated khác tổng VRAM hệ thống. `dicow-runtime.log` chứa chẩn đoán model. Không có timestamp dùng được thì báo lỗi; không tự gán text vào một đoạn toàn file.

```bash
python scripts/compare_dicow.py results/real-source-check/haveasip_13_giang_oi results/dicow-author/haveasip_13 --out results/dicow-author/comparison-haveasip.json
```

Script kiểm tra hai lượt dùng cùng audio. WER/cpWER/DER để null khi chưa có nhãn chuẩn của đúng đoạn thử. Transcript đầy đủ COSV không chấm được trực tiếp đoạn 5 phút; phụ đề YouTube tự động không là ground truth. [Báo cáo so sánh chất lượng](DICOW_COMPARISON.md) bổ sung sáu mẫu VIVOS ghép có reference chữ và bốn mẫu đối chứng cấp cùng nhãn người nói cho cả hai hệ; DER pilot chỉ là sơ bộ vì biên speech chưa được nghe duyệt.

Đây là so sánh **hệ thống** DiariZen+DiCoW với Pyannote+PhoWhisper. Để tách đóng góp conditioning, bước tiếp theo là đối chứng Whisper large-v3-turbo và DiCoW trên cùng diarization/oracle. Adapter đã nhận `--oracle-rttm` để đưa nhãn chuẩn vào STNO; không đưa nhãn chuẩn vào inference thông thường.

## Giới hạn hiện tại

- Greedy decoding (`num_beams=1`), target batch 1; chưa tái lập beam 10 trong thí nghiệm MLC.
- `ctc_weight=0` cho tiếng Việt theo lựa chọn multilingual của tác giả; CTC head có sẵn trong checkpoint nhưng không dùng joint CTC decoding ở lượt này.
- Token log probability và cluster margin không được pipeline tác giả xuất. Adapter để null; confidence còn dùng những tín hiệu sẵn có như độ dài, lặp và overlap, chưa hiệu chỉnh cho DiCoW. Không so sánh RQ3 như hai hệ có cùng đủ tín hiệu.
- Nhận đúng số người chưa chứng minh đúng text hay gán người. Đã có WER/cpWER thăm dò trên pilot VIVOS ghép; chưa có số đo được xác nhận cho ba đoạn audio thực tế hoặc DER với nhãn speech đã nghe duyệt.
- Chưa fine-tune tiếng Việt mới. Khi cần, dùng [training repo](https://github.com/BUTSpeechFIT/TS-ASR-Whisper), dữ liệu audio/text/speaker theo thời gian và split độc lập; không tự nâng nhãn model lên ground truth.

## Colab

[Notebook inference](notebooks/dicow_author_inference.ipynb) dùng cùng adapter và các revision trên. Lấy code trên máy khác bằng `git clone --branch feat/dicow-author-pipeline https://github.com/loanhviet/meeting-asr.git`, rồi cài runtime theo phần trên. Dữ liệu audio, trọng số, kết quả và bundle không nằm trong Git; các đường dẫn artifact trong báo cáo so sánh trỏ tới file local. Muốn dùng notebook Colab, chuẩn bị các sample audio tại đúng đường dẫn rồi tạo bundle để upload:

```bash
python scripts/package_dicow_colab.py --include-samples
```

Bundle chỉ lấy các đường dẫn được liệt kê rõ; không chứa `.env`, token, `.cache`, model weights, SQLite hoặc audio khác. Colab tải checkpoint và tạo runtime riêng. Notebook ghi GPU, thời gian và VRAM rồi cho tải artifact; không có lịch train tự động hoặc cam kết số giờ từ compute units.
