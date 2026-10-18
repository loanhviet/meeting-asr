# So sánh thực nghiệm hệ cũ và DiCoW trên branch thử nghiệm

Branch `feat/dicow-author-pipeline`. Đây là so sánh chất lượng kết quả thật, không dùng model prediction làm reference. Các lượt inference mới tắt LLM, batch 1, bỏ cache inference; trọng số đã nằm trong cache tải model. Máy: RTX 3050 Laptop 4 GB.

## Kết quả cần đọc trước

Trong pilot tiếng Việt có lời chuẩn, **hệ DiCoW tốt hơn về transcript theo người nói**, nhưng **PhoWhisper nhận chữ tốt hơn khi không nói chồng**. Gộp sáu mẫu, cpWER giảm từ 70.06% xuống 27.37%, tương đương giảm 60.9% lỗi tương đối. WER theo thời gian tăng từ 12.55% lên 19.65%. Không được diễn giải mức giảm cpWER này thành mức tăng độ chính xác STT hoặc kết quả đã được xác nhận trên các cuộc họp thật.

Cảm giác DiCoW tốt hơn khi đọc podcast có cơ sở ở một số ví dụ: thuật ngữ tiếng Anh, câu dài và lượt đáp được trình bày rõ hơn. Tuy nhiên, trên COSV và VIVOS vẫn có từ/tên riêng DiCoW nhận kém hơn. Chất lượng cần xét theo cả chữ và người nói.

## Hai hệ được thử

| Thành phần | Hệ cũ | Hệ mới |
|---|---|---|
| Diarization | Pyannote speaker-diarization-3.1 | DiariZen WavLM large s80 **đa miền** |
| ASR | vinai/PhoWhisper-medium | BUT-FIT/DiCoW_v3_MLC |
| Đầu vào ASR | Các đoạn audio cắt theo nhãn diarization | Audio đầy đủ và STNO theo target speaker |
| Gán text cho người | Text kế thừa nhãn của đoạn cắt | Model sinh text cho mỗi target; phụ thuộc STNO |
| Nói chồng | Âm thanh trộn vẫn nằm trong đoạn cắt | FDDT điều kiện hóa nhận dạng theo target/overlap |
| Decode thí nghiệm | Temperature 0, batch 1 | Greedy, beam 1, target tuần tự, FP16, CTC weight 0 |
| Hậu xử lý | Merge gap 0,8 giây, không bỏ filler | Cùng cấu hình merge/filler |

Adapter gọi trực tiếp preprocess, forward và text postprocess từ code tác giả. Revision, package/runtime và chuỗi output gốc nằm trong `dicow-provenance.json`, `dicow-author-output.json`. Đây là checkpoint multilingual tác giả đã fine-tune, chưa fine-tune thêm ở project. DiariZen dùng bản đa miền để thử nguồn trên hai người; chưa dùng đúng bản MLC chuyên hai người. Beam 1 cũng khác beam 10 của kết quả cuối paper. **Không phải tái lập toàn bộ cấu hình benchmark paper.**

Hai hệ thay cả ASR backbone lẫn diarizer. Vì vậy, số đo này chưa tách được đóng góp riêng của FDDT, DiariZen và sự khác biệt PhoWhisper/Whisper turbo. DiCoW vẫn cần diarization; FDDT không đồng nghĩa tách ra waveform sạch của từng người.

## Dữ liệu và cách chấm

1. Ba đoạn thực tế, mỗi đoạn 300 giây: COSV Đức–Ly, COSV Dũng–An, Have A Sip #13. Cùng SHA256 audio giữa hai hệ. COSV có transcript thủ công từ tác giả corpus nhưng không có timestamp. Podcast có phụ đề Việt **tự động**. Không chấm WER/cpWER/DER chính thức cho các đoạn này bằng transcript toàn buổi hoặc phụ đề tự động.
2. Sáu đoạn ghép từ tiếng đọc VIVOS: hai hội thoại gốc, ba người/hội thoại, mỗi hội thoại ở ba điều kiện. Tổng 371.94 giây và 972 token reference, trong đó cùng 324 token được dùng lại ở ba điều kiện. Đây là **hai hội thoại độc lập, không phải sáu cuộc họp độc lập**.
3. Điều kiện: sạch không chồng; sạch chồng khoảng 30%; nhiễu trắng SNR 5 dB không chồng. Nhiễu trắng không mô phỏng đầy đủ tiếng phòng họp, vang phòng, nhạc hay microphone xa.
4. Reference chữ lấy từ VIVOS prompts, ID người nói lấy từ clip nguồn đã dùng khi ghép. Không dùng output ASR làm đáp án. Nhãn biên speech của pilot là `automatic_unverified`; chỉ dùng DER như chẩn đoán sơ bộ.
5. Chuẩn hóa dùng hàm sẵn có của project: NFC, chữ thường, bỏ dấu câu cơ bản, gộp khoảng trắng. Không đổi số, bỏ filler, sửa lỗi reference hay quy đổi từ đồng nghĩa để ưu ái hệ nào. Token tiếng Việt là đơn vị cách trắng, gần mức âm tiết hơn từ ngôn ngữ học.

Các điều kiện dùng lại cùng clip và thứ tự lời, nhưng cách đặt clip/khoảng nghỉ có thể khác nhau; không diễn giải chênh lệch giữa hai điều kiện thành tác động riêng của nhiễu. So sánh hai hệ trong từng điều kiện vẫn dùng đúng cùng file audio. Bộ pilot đọc ghép cũng có thể thuận lợi hơn cho checkpoint chuyên ASR tiếng Việt so với hội thoại tự nhiên.

**WER** = lỗi thay/xóa/thêm token chia số token reference, sau khi nối text theo thời gian và bỏ nhãn người. Khi nói chồng, thứ tự hai lượt cũng có thể làm tăng WER dù nhận đúng chữ; không xem WER này là số đo STT thuần tuyệt đối ở overlap.

**cpWER** = nối text riêng từng người, tìm hoán vị nhãn ít lỗi nhất, rồi cộng lỗi. Tên `SPEAKER_00` không có ý nghĩa đồng nhất giữa hai hệ. cpWER phạt nhầm/gộp/tách người và lỗi chữ; **không phải DER**. Không lấy cpWER trừ WER để gọi đó là tỷ lệ gán sai người. cpWER có thể vượt 100%: lời bị gán vào người không tương ứng có thể tạo cả deletion ở người thật và insertion ở người sai.

## Kết quả pilot với diarization dự đoán

| Điều kiện | WER hệ cũ | WER DiCoW | cpWER hệ cũ | cpWER DiCoW |
|---|---:|---:|---:|---:|
| Sạch, không chồng | 6.17% | 15.12% | 45.68% | 20.68% |
| Nhiễu trắng SNR 5 dB, không chồng | 12.35% | 25.62% | 102.16% | 39.81% |
| Sạch, chồng ~30% | 19.14% | 18.21% | 62.35% | 21.60% |
| Gộp 6 mẫu | 12.55% | 19.65% | 70.06% | 27.37% |


![WER và cpWER](results/dicow-author/quality-pilot/quality-comparison.png)

- Sạch không chồng: PhoWhisper nhận chữ tốt hơn rõ. Trong mẫu `test_001`, hệ cũ nhận 2 người thay vì 3, có WER 2,67% nhưng cpWER 55,08%; DiCoW có WER/cpWER cùng 12,30%. Nhận chữ đúng vẫn có thể cho biên bản sai người.
- Nhiễu 5 dB: WER hệ cũ vẫn thấp hơn. Tuy nhiên, diarizer cũ trả 1 người cho `test_001` và 2 người cho `test_002`; DiariZen trả 3 người ở cả hai. cpWER hệ mới giảm mạnh. DiCoW vẫn có lỗi nhận âm/từ khi nhiễu.
- Chồng 30%: WER hai hệ gần nhau (19.14%/18.21%), cpWER DiCoW thấp hơn rõ. Số deletion theo WER giảm từ **27 xuống 3**, insertion từ **11 xuống 1**; substitution tăng từ **24 lên 55**. Hệ mới giữ được nhiều token hơn nhưng vẫn nhận nhầm token. Đây là đặc điểm có ích cho transcript nhiều người, chưa chứng minh loại bỏ toàn bộ lỗi overlap.
- Gộp: hệ cũ có 83 substitution, 27 deletion, 12 insertion; DiCoW có 179 substitution, 4 deletion, 8 insertion. Do vậy, đọc thấy câu đủ hơn có thể đồng thời đi với nhiều lỗi thay chữ hơn.

Kết quả từng mẫu:

| Hội thoại gốc | Điều kiện | Người cũ/mới (chuẩn: 3) | WER cũ/mới | cpWER cũ/mới |
|---|---|---:|---:|---:|
| test_001 | ovl0_clean | 2/3 | 2.67%/12.30% | 55.08%/12.30% |
| test_001 | ovl0_snr5 | 1/3 | 11.23%/28.34% | 128.88%/43.32% |
| test_001 | ovl30_clean | 2/3 | 17.65%/20.32% | 59.36%/20.32% |
| test_002 | ovl0_clean | 3/3 | 10.95%/18.98% | 32.85%/32.12% |
| test_002 | ovl0_snr5 | 2/3 | 13.87%/21.90% | 65.69%/35.04% |
| test_002 | ovl30_clean | 2/3 | 21.17%/15.33% | 66.42%/23.36% |


DiCoW thắng cpWER ở cả sáu mẫu, nhưng mức thắng mẫu sạch `test_002` rất nhỏ: 32,85% → 32,12%. Không được chỉ chọn mẫu sạch `test_001` để đại diện cho cả tập. Không tính p-value hoặc khẳng định ý nghĩa thống kê từ hai hội thoại này.

## Đối chứng dùng chung nhãn người nói

Cả hai hệ được cấp **cùng RTTM từ vị trí clip nguồn trong bộ trộn**, gồm danh tính và khoảng đặt clip. Nhãn này biết chính xác từ cách dựng audio, nhưng chứa cả khoảng im lặng nội bộ clip, không phải speech boundary đã nghe duyệt. Với hệ cũ, RTTM quyết định audio cắt; với DiCoW, RTTM tạo STNO. Âm thanh ở đoạn overlap vẫn là âm thanh trộn, không đưa waveform riêng của mỗi người vào ASR.

| Hội thoại | Điều kiện | cpWER oracle PhoWhisper | cpWER oracle DiCoW |
|---|---|---:|---:|
| test_001 | ovl0_clean | 3.74% | 14.97% |
| test_001 | ovl30_clean | 19.79% | 19.25% |
| test_002 | ovl0_clean | 10.95% | 21.17% |
| test_002 | ovl30_clean | 37.23% | 18.25% |


- Không nói chồng: cpWER oracle PhoWhisper **6.79%**, DiCoW **17.59%**.
- Chồng ~30%: cpWER oracle PhoWhisper **27.16%**, DiCoW **18.83%**.


Đối chứng này giảm ảnh hưởng sai phân cụm người, giúp xem khác biệt nhận chữ và cơ chế xử lý overlap. Nó vẫn không cô lập FDDT vì hai ASR backbone khác nhau; kết quả cần đọc cùng dạng dữ liệu đọc ghép và cách đặt clip.

Khi giảm lỗi phân cụm, PhoWhisper thắng rõ trên tiếng sạch; DiCoW thắng ở nhóm overlap. Vì vậy, phần lớn khoảng cách cpWER của hệ hoàn chỉnh trên dữ liệu không chồng đến từ diarization/speaker attribution, còn lợi thế xử lý tiếng chồng vẫn xuất hiện khi cấp chung nhãn. Không coi RTTM vị trí clip này là cận trên accuracy: nó chứa im lặng nội bộ và khác mask speech dự đoán; thay mask/cách cắt có thể làm điểm tăng hoặc giảm.

## Diarization: DER chỉ là chẩn đoán sơ bộ

Relaxed dùng collar 0,25 giây và bỏ overlap. Strict dùng collar 0 và giữ overlap. Reference speech intervals chưa nghe xác nhận; số này **không đủ để báo cáo chất lượng diarization đã nghiệm thu**.

| Hội thoại | Điều kiện | DER relaxed cũ/mới | DER strict cũ/mới |
|---|---|---:|---:|
| test_001 | ovl0_clean | 35.76%/13.06% | 41.22%/20.52% |
| test_001 | ovl0_snr5 | 63.59%/20.57% | 66.90%/27.57% |
| test_001 | ovl30_clean | 27.47%/7.54% | 40.36%/20.65% |
| test_002 | ovl0_clean | 23.99%/21.31% | 33.27%/30.94% |
| test_002 | ovl0_snr5 | 36.81%/21.55% | 44.25%/31.18% |
| test_002 | ovl30_clean | 30.73%/17.16% | 42.19%/29.72% |


DiariZen có DER thấp hơn trên sáu mẫu theo nhãn tự động đang có. Ví dụ sạch `test_001`: confusion relaxed hệ cũ 22,82%, DiariZen 0%; miss lần lượt 12,94% và 13,06%. Ở mẫu này, lợi thế chủ yếu nằm ở phân biệt người, không phải phát hiện nhiều speech hơn. Ở `test_002` vẫn còn confusion và miss; trả đúng ba nhãn chưa chứng minh đúng tất cả lượt nói.

## Các ví dụ trên audio thực tế

Đây là đọc và đối chiếu artifact/reference text; **chưa có người nghe duyệt độc lập**, không trình bày thành transcript audio đã xác nhận.

| Vị trí trong mẫu | Quan sát output | Ý nghĩa |
|---|---|---|
| Have A Sip, ~19–35s | PhoWhisper viết loanword thành `kô bờ lu`/`cô bờ riu`; DiCoW viết `cold brew` | Cách viết thuật ngữ ở DiCoW dễ đọc hơn; không dùng caption tự động để tuyên bố tỷ lệ đúng |
| Have A Sip, ~275–278s | Hệ cũ nhập lời về giàn phơi và lời đáp vào một người; DiCoW chia hai lượt | Có lợi cho trình bày hội thoại; phải nghe kiểm tra danh tính/timing trước khi gọi nhãn đúng |
| COSV Đức–Ly, ~42,5–46,5s | Câu hỏi và tự giới thiệu Ly nằm cùng nhãn ở hệ cũ; DiCoW tách câu hỏi khỏi câu trả lời | Phù hợp cấu trúc hai speaker liên tiếp trong transcript nguồn |
| COSV Đức–Ly, ~164–181s | Hệ cũ nhập câu đáp của Ly vào câu hỏi dài của người phỏng vấn; DiCoW xuất lượt Ly khoảng 166,88–169,18s | Ví dụ cụ thể về lợi ích speaker attribution; lời đáp vẫn có lỗi chữ |
| COSV Đức–Ly, ~25s | Tên chuẩn `phạm lê quý đức`: hệ cũ giữ đúng, DiCoW viết `phạm lê quỷ đức` | DiCoW chưa tốt hơn đồng đều ở tên riêng |
| COSV Đức–Ly, ~285,5s | Chuẩn `bãi đất trống`: hệ cũ thành `bãi nước trống`; DiCoW thành `bãi chất chấm` | Cả hai sai, DiCoW có lỗi thay chữ nặng hơn |
| Have A Sip, ~60–64s | DiCoW có hai target cùng xuất lời gần giống nhau về pha cà phê | Dấu hiệu cần kiểm tra lặp/gán nhầm khi overlap; conditioning chưa bảo đảm hoàn toàn |

COSV còn có vấn đề nhãn nguồn: Đức–Ly có ba label trần `spk` được parser ban đầu nối vào lượt trước; mình đã tách lại thành lượt chưa biết người, cập nhật checksum và tắt chấm speaker trong metadata. Dũng–An có self-introduction/speaker labels thiếu nhất quán và `spk34` ở phần khác. Không dùng nguồn chưa audit để chấm cpWER chính thức.

**Dũng–An:** cả buổi có bốn label, nhưng phần reference ứng với năm phút đầu chưa tới lượt `spk4` đầu tiên. Hệ cũ trả 4 nhãn, DiCoW trả 3 nhãn; riêng nhãn thứ tư hệ cũ chỉ có năm utterance, tổng khoảng 2,67 giây. Có thể là phân mảnh người nói hoặc lời đáp chưa được nguồn chép đầy đủ; không thể kết luận bằng đếm nhãn rằng hệ nào mất/thêm đúng một người.

Không cắt transcript toàn buổi bằng cách tìm đoạn khiến model đạt WER thấp nhất. Muốn số đo đáng tin cậy trên audio thực tế cần reference của đúng khoảng thời gian và audit nhãn độc lập.

## Tốc độ và khả năng chạy

| Audio thực tế 300 giây | Thời gian hệ cũ | Thời gian DiCoW | Người cũ/mới | Lượt hiển thị cũ/mới |
|---|---:|---:|---:|---:|
| COSV Đức–Ly | 87.94s | 76.33s | 3/3 | 84/112 |
| COSV Dũng–An | 79.65s | 75.39s | 4/3 | 99/126 |
| Have A Sip #13 | 65.62s | 87.75s | 2/2 | 34/67 |


Thời gian gồm nạp model, khởi tạo runtime và xử lý. Cả hai dùng inference không cache. Một lượt trên mỗi audio, không phải benchmark latency lặp. Trên ba đoạn thực tế, tốc độ không có ưu thế nhất quán: DiCoW nhanh hơn hai đoạn COSV nhưng chậm hơn podcast. Số lượt hiển thị nhiều hơn phản ánh chia đoạn/merge, không đo accuracy.

Pilot sáu mẫu: hệ cũ tổng 180.60s, DiCoW 169.38s trên 371.94s audio. Khoảng cách nhỏ; chưa kết luận hệ mới luôn nhanh hơn. Provenance COSV ghi peak CUDA allocated khoảng **0,63 GiB cho DiariZen** và **1,99 GiB cho DiCoW** khi nạp hai stage tuần tự. Đây không phải tổng VRAM `nvidia-smi`; inference đã chạy được trên GPU 4 GB. Không suy ra từ đó bộ nhớ cần khi fine-tune.

## Đối chiếu với tác giả và hướng triển khai

[Model card chính thức](https://huggingface.co/BUT-FIT/DiCoW_v3_MLC) công bố Vietnamese tcpWER 24,7% cho hệ fine-tuned với diarization thực và 15,3% với nhãn chuẩn. Đây là benchmark của tác giả, không phải baseline PhoWhisper project và không so trực tiếp với cpWER pilot ở đây. [Paper MLC](https://arxiv.org/html/2506.13414v1) dùng bài toán hai người; profile project đang dùng DiariZen đa miền và greedy. Không kỳ vọng bê nguyên phần trăm paper sang cuộc họp 3–4 người tiếng Việt.

Với project hiện tại, DiCoW là hướng thử nghiệm có ích cho **transcript ai nói gì**, đặc biệt khi có chồng tiếng. Cần giữ PhoWhisper làm đối chứng nhận chữ: checkpoint chuyên tiếng Việt đang tốt hơn trên lời đọc sạch/nhiễu của pilot. Chưa có lý do bỏ baseline hoặc vội fine-tune chỉ từ cảm giác đọc podcast.

[PhoWhisper](https://huggingface.co/vinai/PhoWhisper-medium) được tác giả fine-tune trên 844 giờ tiếng Việt nhiều vùng giọng; DiCoW MLC phục vụ nhận dạng hội thoại đa ngôn ngữ theo target speaker. Đây là khác biệt mục tiêu/dữ liệu huấn luyện cần xét khi đọc kết quả, chưa phải bằng chứng nguyên nhân cho từng lỗi.

Trước fine-tune, nên ưu tiên: (1) nghe duyệt reference khoảng 10–20 phút của các đoạn thực tế đã có; (2) bổ sung cuộc họp thực với microphone xa và 3–4 người; (3) so DiCoW/Whisper turbo trên cùng diarization để tách tác dụng conditioning; (4) thử beam 10 ở một subset cố định, ghi cả chất lượng và chi phí. Đây là bước tiếp theo được đề xuất, chưa được tự chạy hay công bố là hoàn thành.

Confidence hiện chưa so sánh công bằng: adapter DiCoW không có token logprob/no-speech/cluster margin đầy đủ, để null; confidence chỉ dùng tín hiệu còn lại và chưa hiệu chỉnh. Không dùng điểm màu trên UI để kết luận một model chắc chắn hơn. LLM tắt nên chưa đo chất lượng tóm tắt/Q&A hoặc tác động lỗi transcript đến phần đó.

## Artifact và tái kiểm tra

- [Scores JSON](results/dicow-author/quality-pilot/scores.json): error counts, best speaker mapping, text nguồn/model, cache flags, SHA256 audio và source code.
- [Manifest pilot](results/dicow-author/quality-pilot/manifest.json): nguồn clip, reference, điều kiện, annotation status.
- [Biểu đồ PNG](results/dicow-author/quality-pilot/quality-comparison.png), [SVG](results/dicow-author/quality-pilot/quality-comparison.svg).
- Mỗi folder giữ `run.json`, `transcript.json`, `diarization.rttm`; folder DiCoW có output gốc/provenance. Folder `*-oracle` chỉ dùng trong đối chứng.
- [Tích hợp và pin model](DICOW.md); [script chấm](scripts/score_dicow_quality.py).

Chấm lại artifact (không chạy model, không upload web):

```bash
.venv/bin/python scripts/score_dicow_quality.py results/dicow-author/quality-pilot
```

Ví dụ chạy lại một mẫu; đổi config thành `configs/dicow-author.yaml` để chạy hệ mới, thêm `--oracle-rttm` trỏ tới `.oracle.rttm` tương ứng cho đối chứng:

```bash
MEETING_LLM_ENABLED=false MEETING_ASR_BATCH_SIZE=1 .venv/bin/meeting-asr run data/simulated/pilot-speech/sim_ovl0_clean_spk3_001.wav --config configs/default.yaml --out results/dicow-author/recheck --no-cache
```

Validation implementation: 126 tests Python pass, Ruff pass; package source/wheel build thành công. Những kiểm tra code này không thay thế kiểm định accuracy model. Branch thử nghiệm riêng, chưa merge vào main và chưa fine-tune thêm tiếng Việt.
