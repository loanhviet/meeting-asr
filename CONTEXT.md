# Context để tiếp tục triển khai — 12/10/2026

## Cập nhật bàn giao — 18/10/2026

Code, cấu hình, test, notebook và tài liệu DiCoW được bàn giao qua branch `feat/dicow-author-pipeline` trên remote `origin`. Các ghi chú “chưa commit/push” bên dưới mô tả snapshot ngày 12/10; dùng `git status` và `git log` để kiểm tra trạng thái hiện tại. Fix proxy upload web được lưu trong commit riêng.

Kiểm tra lại ngày 18/10: 126 tests Python đạt, Ruff check/format đạt; web typecheck và format đạt. Chưa chạy thêm model hoặc đánh giá chất lượng mới. Audio demo trong `document/`, CSV thí nghiệm và artifact `results/dicow-author/` vẫn ở local; clone branch không tự có dữ liệu, trọng số hoặc bundle Colab.

## Snapshot phiên 12/10/2026

Cập nhật lúc khoảng 23:44, múi giờ Asia/Bangkok. Đọc file này cùng [DICOW.md](DICOW.md) và [DICOW_COMPARISON.md](DICOW_COMPARISON.md) trước khi tiếp tục. Đây là ghi nhận quyết định mới nhất của chủ project; các tài liệu mô tả phạm vi cũ cần được đối chiếu với quyết định này.

## Quyết định đã thống nhất với người dùng

- **DiariZen + DiCoW theo kiến trúc tác giả là hướng phát triển/nghiên cứu chính** cho transcript cuộc họp nhiều người, đặc biệt speaker attribution và nói chồng.
- Giữ Pyannote/ECAPA + PhoWhisper làm **baseline đối chứng**. PhoWhisper vẫn có lợi thế nhận chữ trên các mẫu tiếng Việt sạch/nhiễu không chồng của pilot.
- Đây là quyết định về hướng phát triển, chưa phải kết luận DiCoW thắng ở mọi audio hoặc đủ chất lượng để thay toàn bộ hệ đang dùng.
- Người dùng muốn so sánh chất lượng kỹ; **không cần upload tất cả kết quả lên website**. Ưu tiên đánh giá, reference và artifact local.
- Chưa fine-tune thêm. Người dùng có Colab Pro và nói còn khoảng 300 compute units; chưa xác minh số dư/loại GPU, chưa coi đây là số giờ GPU đảm bảo hoặc ngân sách huấn luyện đã xác định.
- Notebook Colab đã chuẩn bị, chưa được chạy kiểm chứng trên Colab. Inference mới đã chạy thật trên GPU local.

## Vì sao ban đầu tham khảo DiCoW nhưng triển khai khác?

Bằng chứng nằm trong tài liệu local `docs/CSE457_Spec_KyThuat_v2_1.md`, §9.1–9.2 và bảng quyết định cuối tài liệu:

- Spec chủ động chọn **cascaded**: diarization → audio cuts → ASR. Paper dùng cho tổng quan, động cơ đo lỗi diarization lan truyền và các câu hỏi nghiên cứu; không yêu cầu tái lập kiến trúc tác giả.
- FDDT/QK-biasing được đặt ngoài phần cài đặt; huấn luyện bị loại khỏi phạm vi ban đầu. Đây là quyết định ghi trong spec, không thể chỉ quy thành lỗi code khác sơ đồ.
- Spec còn dựa trên nhận định checkpoint tác giả fine-tune tiếng Anh nên không dùng lại được cho tiếng Việt. **Nhận định này không còn đúng với checkpoint đa ngôn ngữ hiện có**: đã xác minh và dùng `BUT-FIT/DiCoW_v3_MLC`, có kết quả tiếng Việt của tác giả.
- Không cần tự huấn luyện lại FDDT để thử inference bằng checkpoint pretrained. Cần phân biệt việc tái huấn luyện paper với việc tích hợp kiến trúc/trọng số tác giả đã huấn luyện.
- Tài liệu chưa cung cấp bằng chứng để khẳng định khi viết spec ban đầu checkpoint nào đã có sẵn. Không suy diễn lịch sử đó; vấn đề hiện tại là phải cập nhật quyết định dựa trên checkpoint đã xác minh.

Tham khảo paper để xây baseline khác kiến trúc có thể là phạm vi nghiên cứu hợp lệ nếu trình bày rõ. Với mục tiêu mới của người dùng, **cần theo DiCoW làm hướng chính**, giữ baseline để đối chứng và cập nhật spec/báo cáo cho nhất quán. Không gọi hệ cascaded cũ là implementation DiCoW.

Spec local đã có phụ lục điều chỉnh ngày 12/10, nhưng phần §9 cũ và một số tài liệu kiến trúc vẫn mô tả phạm vi cũ; chưa hoàn tất chuyển toàn bộ tài liệu. Đừng lấy các câu “không cài đặt FDDT” cũ để tự đảo ngược quyết định mới của người dùng.

## Git và hiện trạng code

- Workspace: `/home/viet/projects/TLU/meeting_asr`.
- Branch: `feat/dicow-author-pipeline`, tạo từ `27d07e9ccdef9b0254899f1b8830ec94bead611b` trên main.
- **Các thay đổi DiCoW và báo cáo hiện vẫn ở working tree, chưa commit/push/merge.** Kiểm tra `git status` trước khi làm tiếp; không reset/clean hoặc add toàn bộ thư mục.
- `document/` và các artifact `results/` có từ công việc trước, cần giữ. `docs/`, `data/`, `.cache/` bị gitignore; file trong đó không đi theo commit mặc định.
- `web/next.config.ts` đang có fix proxy upload khoảng 200 MiB từ phiên sửa lỗi upload trước; giữ thay đổi này, không nhầm thành phần thuật toán DiCoW.
- Cấu hình CLI mặc định vẫn là baseline. Hướng nghiên cứu chính đã chọn DiCoW nhưng **chưa đổi default toàn project/Docker**.

Implementation đã có:

- `src/meeting_asr/dicow.py`: bridge từ pipeline project sang runtime tác giả, parse timestamp thật, cache/provenance; không bịa timestamp toàn file cho output không có timestamp.
- `src/meeting_asr/dicow_runner.py`: gọi DiariZen và trực tiếp preprocess/forward/postprocess của code DiCoW tác giả. Audio đầy đủ + STNO/FDDT theo target, không đưa audio cuts vào PhoWhisper.
- `src/meeting_asr/pipeline.py`: dispatch baseline/DiCoW, cache joint M2/M3, lưu RTTM gốc và output model.
- `configs/dicow-author.yaml`, `scripts/setup_dicow.py`, `requirements/dicow*.txt`: runtime/model pins riêng.
- CLI `run` và `experiments` hỗ trợ profile DiCoW/DiariZen; API health xuất engine/model/backend.
- `scripts/compare_dicow.py`: đối chiếu cùng audio, để quality null nếu không có reference đúng đoạn.
- `scripts/score_dicow_quality.py`: chấm pilot chữ/speaker, DER gắn nhãn sơ bộ, giữ mapping/error counts/SHA256.
- `notebooks/dicow_author_inference.ipynb`, `scripts/package_dicow_colab.py`: thử inference Colab bằng bundle whitelisted, không chứa credentials/weights/SQLite.
- `tests/test_dicow.py`: kiểm tra timestamp thật, reject span sai, cache joint và invalidation.

Runtime baseline `.venv` được giữ nguyên. Runtime tác giả nằm trong `.cache/dicow/venv`, checkout trong `.cache/dicow/upstream/DiCoW`. Transformers tác giả dùng **4.42.4** để tương thích custom code MLC; không tự nâng lên 4.55+ mà chưa kiểm tra API.

Pins và cấu hình:

- DiCoW upstream: `801e2130d00142a7da5845754f87b97550053a75`.
- DiariZen submodule: `4d1009d4a3f1bc41777623e9d74b8081564cddf9`.
- `BUT-FIT/DiCoW_v3_MLC`: `99c64e8dc409a158816e808a1ee556cdfd0af51c`.
- `BUT-FIT/diarizen-wavlm-large-s80-md`: `6285693ddd5b38e8229acb93f864f3d04a82bee1`.
- WeSpeaker embedding: `837717ddb9ff5507820346191109dc79c958d614`.
- Decode target tuần tự, FP16 trên CUDA, beam 1, CTC weight 0 cho tiếng Việt. DiariZen giải phóng trước khi nạp DiCoW để chạy GPU local 4 GB.
- Đây là checkpoint MLC mới theo hướng tác giả, **không phải tái huấn luyện paper v1 hoặc tái lập nguyên cấu hình benchmark**. Diarizer đang dùng bản đa miền, paper MLC dùng bản chuyên hai người; decode paper cuối dùng beam 10.

## Kết quả thật đã đo

Pilot: 2 hội thoại gốc × 3 điều kiện, 3 người/hội thoại, 371,94 giây audio. Reference 324 token nguồn được dùng lại ở ba điều kiện, tổng chấm 972 token. **Không coi sáu điều kiện là sáu cuộc họp độc lập.** Chữ lấy từ VIVOS prompts; người lấy từ clip nguồn. Hai hệ chạy cùng file/SHA256 trong từng cặp, LLM tắt, batch 1, inference cache miss.

| Điều kiện | WER baseline | WER DiCoW | cpWER baseline | cpWER DiCoW |
|---|---:|---:|---:|---:|
| Sạch, không chồng | 6,17% | 15,12% | 45,68% | 20,68% |
| Nhiễu trắng SNR 5 dB | 12,35% | 25,62% | 102,16% | 39,81% |
| Sạch, chồng ~30% | 19,14% | 18,21% | 62,35% | 21,60% |
| Gộp | 12,55% | 19,65% | 70,06% | 27,37% |

Đã chạy thêm 8 lượt đối chứng trên 4 mẫu, cấp cùng RTTM vị trí clip cho hai hệ:

| Điều kiện | cpWER oracle PhoWhisper | cpWER oracle DiCoW |
|---|---:|---:|
| Sạch không chồng | 6,79% | 17,59% |
| Chồng ~30% | 27,16% | 18,83% |

Kết luận: hệ mới cải thiện transcript theo người, DiariZen góp phần đáng kể; DiCoW có lợi thế overlap ngay cả khi cấp chung nhãn. PhoWhisper nhận chữ tốt hơn khi không chồng. Hai backbone khác nhau nên chưa cô lập tác dụng FDDT. RTTM oracle là vị trí toàn clip, có cả im lặng nội bộ; chưa phải speech boundary được nghe duyệt hoặc cận trên accuracy.

Artifact:

- `results/dicow-author/quality-pilot/scores.json`, `manifest.json`, `quality-comparison.png`, `quality-comparison.svg`.
- Mỗi mẫu trong `test_001/` hoặc `test_002/` có `baseline/`, `dicow/`; mẫu sạch/chồng có thêm `baseline-oracle/`, `dicow-oracle/`.
- Báo cáo diễn giải, từng mẫu và lỗi cụ thể: [DICOW_COMPARISON.md](DICOW_COMPARISON.md).
- 126 tests Python pass, Ruff pass, source/wheel build thành công. Đây là verification code, không phải nghiệm thu accuracy trên cuộc họp thực.

Ba đoạn thực tế cũng đã chạy cả hai hệ:

- COSV Đức–Ly: `data/real/cosv_duc_ly/sample_first_5min.wav`.
- COSV Dũng–An: `data/real/cosv_dung_an/sample_first_5min.wav`.
- Have A Sip #13: `data/real/haveasip_13_giang_oi/sample_5min.wav`, tương ứng 01:30–06:30 nguồn.
- Baseline ở `results/real-source-check/`; DiCoW ở `results/dicow-author/{cosv_duc_ly,cosv_dung_an,haveasip_13}/`.

## Giới hạn phải giữ khi báo cáo

- Pilot là tiếng đọc ghép, hai hội thoại; chưa suy rộng thành chất lượng cuộc họp tiếng Việt thật.
- WER nối theo thời gian có thể chịu ảnh hưởng thứ tự lượt overlap. cpWER gồm lỗi chữ và gán người; không lấy cpWER trừ WER để gọi đó là tỷ lệ diarization sai.
- DER pilot chỉ sơ bộ: nhãn speech `automatic_unverified`. Không dùng làm DER được nghiệm thu.
- COSV có transcript thủ công nhưng không timestamp; reference toàn buổi không chấm trực tiếp clip 5 phút. Đức–Ly có 3 marker `spk` thiếu số đã tách thành unknown, cập nhật checksum và tắt speaker scoring. Dũng–An có nhãn mơ hồ/thiếu nhất quán, trong đó `spk34`.
- Dũng–An có 4 label trong cả buổi nhưng reference năm phút đầu chưa tới `spk4`. Baseline trả 4, DiCoW trả 3; **không kết luận DiCoW bỏ sót người chỉ từ con số này**.
- Phụ đề Việt của podcast là tự động; không dùng làm gold WER. Bản dịch Anh không thay reference Việt.
- Confidence DiCoW thiếu token logprob/cluster margin, để null và chưa calibration. Không so màu/điểm UI như hai hệ có cùng đủ tín hiệu. Giữ RQ3 nhưng cần thiết kế lại đánh giá phù hợp hướng mới.
- LLM tắt trong thí nghiệm. Phiên chạy trước gặp HTTP 403 ở provider; chưa sửa vấn đề này, chưa đánh giá summary/Q&A với transcript mới.
- Thời gian gồm nạp model, không có benchmark lặp. Chạy được trên GPU 4 GB không chứng minh đủ VRAM fine-tune.

## Việc tiếp theo — chưa triển khai

1. Chốt/cập nhật spec và tài liệu kiến trúc: DiCoW là hướng chính, cascaded là baseline; phân biệt tích hợp pretrained với tái huấn luyện/tái lập paper. Giữ đóng góp confidence/RQ3, audit lại giả định khi thiếu tín hiệu.
2. Nghe duyệt reference của đúng đoạn thực tế (ưu tiên 10–20 phút), xác nhận chữ, người nói và speech/overlap timestamps. Không tạo gold bằng output của hai model đang so.
3. Đánh giá trên reference đó bằng WER/cpWER; DER chỉ khi speech/timestamp đã được xác minh. Giữ split/calibration độc lập, chưa vội báo cáo thắng chung.
4. Đối chứng Whisper large-v3-turbo với DiCoW trên cùng diarization để giảm khác biệt backbone; thử beam 10 trên subset cố định và ghi chi phí. **Chưa chạy các đối chứng này.**
5. Khi lỗi tiếng Việt/miền cuộc họp đã rõ, lập kế hoạch fine-tune theo training repo tác giả, dữ liệu có nhãn và GPU Colab thực tế. **Chưa chuẩn bị xong dataset train hoặc bắt đầu training.**

## Lệnh tiếp tục và dịch vụ local

```bash
git status --short
git branch --show-current
# Chấm lại artifact, không chạy model hoặc upload web:
.venv/bin/python scripts/score_dicow_quality.py results/dicow-author/quality-pilot
# Inference DiCoW khi cần chạy thêm một audio:
MEETING_LLM_ENABLED=false .venv/bin/meeting-asr run data/real/cosv_duc_ly/sample_first_5min.wav --config configs/dicow-author.yaml --out results/dicow-author/recheck
```

Cuối phiên, theo yêu cầu người dùng, **đã dừng API và web**, xác nhận cổng 8000/3000 không còn listener. Trước khi dừng, server dùng profile DiCoW, LLM tắt. Process record: `results/local-runtime/processes-20261012-231242.json`; PID cũ không dùng để thao tác ở phiên sau. Không tự restart server hoặc upload thêm chỉ để tiếp tục đọc kết quả.

Người dùng hiện làm nhóm hai người; thành viên mới clone GitHub vẫn thấy baseline vì code DiCoW còn ở branch local chưa commit/push. Giải thích thay đổi hướng là kết quả kiểm tra lại checkpoint và chạy đối chứng; không khẳng định trước kia chưa tồn tại checkpoint đa ngôn ngữ khi chưa xác minh lịch sử phát hành. Việc đưa branch lên GitHub để cộng tác chưa thực hiện.

Bundle Colab local: `results/dicow-author/colab-bundle.zip`; giữ cùng notebook trong `notebooks/`. Các file dữ liệu và runtime local không được đảm bảo có trên máy khác; cần kiểm tra tồn tại trước khi tải/cài lại. Không ghi hoặc commit `.env`, token, audio nguồn/weights hoặc SQLite cùng code.
