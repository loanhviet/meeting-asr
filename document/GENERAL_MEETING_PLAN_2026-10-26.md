# Kế hoạch hoàn thiện cho cuộc họp tiếng Việt thông thường

Cập nhật 26/10/2026. Mục tiêu bao gồm nhận chữ, xác định ai nói gì, soát sửa,
biên bản và hỏi đáp có dẫn chứng. Họp IT là một nhóm tình huống trong phạm vi
này. Kết quả và giới hạn của lượt đo nằm trong
[báo cáo đánh giá](GENERAL_MEETING_EVALUATION_2026-10-26.md).

Đã hoàn tất vòng triển khai đầu trên dev riêng: scorer MeetEval, beam 1/3/5,
40 đối chứng PhoWhisper và chẩn đoán LLM. Xem
[kết quả vòng 1](ASR_IMPROVEMENT_ROUND1_2026-10-26.md). Beam 3 chỉ giảm một
lỗi tiếng Việt, beam 5 gặp lặp text; giữ mặc định beam 1. LLM trả
`insufficient_quota`; bộ họp tiếng Việt có nhãn đã nghe rà và nghiệm thu
semantic vẫn là việc tiếp theo, chưa training.

## Cơ sở chọn thứ tự công việc

- DiCoW hiện có WER 14,94% trên 40 clip FLEURS, 20,82% trên 63 clip ViMD và
  24,19% trên 27 clip VietMed. Đây là các phép thử bổ sung, khác miền.
- Giữ nguyên tiền xử lý và timeline DiariZen dự đoán, PhoWhisper có WER tương
  ứng 12,56%, 16,54% và 23,05%. Phần nhận chữ có dư địa cải thiện ngay cả khi
  không thay diarizer. Chưa suy rộng kết quả clip ngắn sang họp nói chồng.
- Một hội thoại COSV đầy đủ gần 47 phút có WER thăm dò 29,17%; transcript
  nguồn cần rà quy ước từ đệm và phần đầu/cuối, chưa có timestamp speaker chuẩn.
- Cùng một đoạn AMI, WER headset 24,54% và microphone phòng 39,69%. AMI là
  tiếng Anh và được model card nêu trong dữ liệu huấn luyện; phép thử này chỉ
  giúp xác định điều kiện cần kiểm tra thêm bằng tiếng Việt.
- Bộ ViYT-Diar có 97 file hai nhãn speaker và 3 file một nhãn; overlap trung bình
  theo file chỉ khoảng 0,66%. Bộ này chưa bao phủ họp đông người/chồng tiếng nặng.
- DER trên toàn bộ 100 file là 14,07% strict / 7,83% relaxed. Ba file chỉ có
  nhãn Speaker_2 ở phần muộn cần nghe rà; đã xác nhận parquet gốc và RTTM khớp.
  Giữ chúng trong điểm chính, báo phân tầng để làm rõ độ nhạy tham chiếu.
- Cấu hình biên bản hiện tại (`qwen3.7-max`) trả HTTP 403 trong canary thật.
- Trên 237 câu hỏi cụ thể thuộc 35 cuộc họp QMSum validation, retrieval hiện
  lấy trúng ít nhất một vùng nguồn được gán nhãn ở 173 câu. Tăng `top_k` từ 6
  lên 12, giữ cap 12.000 ký tự, đạt 200 câu; tăng cap lên 24.000 chỉ thêm một
  câu. Đây là chẩn đoán tìm nguồn tiếng Anh, chưa phải điểm đúng của câu trả lời.

## Mốc 1 — Bộ nghiệm thu sát sản phẩm và LLM truy cập được

Nghe kiểm tra ba file ViYT được đánh dấu trong `diagnostics.json` trước khi
quy toàn bộ false alarm của chúng thành lỗi model hoặc sửa nhãn nguồn.

Chuẩn bị khoảng **8 cuộc họp tiếng Việt, mỗi bản 6–10 phút**. Đây là quy mô
đề xuất cho vòng nghiệm thu đầu, không phải số dữ liệu đã có hoặc bảo đảm đại
diện mọi cuộc họp.

- Phủ họp điều phối công việc, thảo luận kế hoạch, họp nhóm học tập/chuyên môn
  và tổ chức hoạt động. Có thể bổ sung một tình huống IT.
- Có cả 2 người, 3–4 người và 5–6 người; có microphone phòng/điện thoại,
  khác vùng giọng, lượt ngắn và đoạn nói chồng.
- Chép nội dung đúng audio; thống nhất cách giữ từ đệm, từ lặp và viết số.
  Gán người nói, khoảng speech/overlap và đánh dấu đoạn không nghe rõ.
- Một người chép, một người kiểm tra chéo các đoạn khó và các câu chứa
  quyết định, tên, số, phủ định, người phụ trách hoặc thời hạn.
- Tách dev/test theo **cuộc họp gốc** trước khi tuning; ưu tiên tách người
  nói khi khả thi. Ghi rõ phần trùng, không chia các đoạn cùng recording sang
  hai phía rồi coi là độc lập.

Đồng thời kiểm tra quyền truy cập/model/endpoint của cấu hình LLM đã chọn,
chạy một canary công khai thành công, lưu model/prompt và metadata đã khử key.
`llm-check` mặc định chỉ xác nhận đủ cấu hình. Vòng triển khai đầu đã bổ sung
`llm-check --probe` để gửi một canary ngắn và ghi HTTP/provider code;
xem [quy trình](ASR_IMPROVEMENT_WORKFLOW.md). Canary vẫn cần thành công trước
khi chấm chất lượng biên bản/hỏi đáp qua API này.

**Đầu ra:** manifest có nguồn/checksum/split; transcript, RTTM/UEM đã soát;
quy ước chấm; câu hỏi và đáp án/dẫn chứng giữ riêng; canary biên bản thành công.

## Mốc 2 — Chọn nhánh nhận chữ và cấu hình diarization trên dev

DiCoW tiếp tục là hướng nghiên cứu chính. So sánh trên cùng audio và cùng quy
ước tham chiếu:

1. DiariZen + DiCoW hiện tại.
2. DiariZen + PhoWhisper theo nhánh đối chứng đã chuẩn bị.
3. Nếu cần phân tích thêm, Whisper large-v3-turbo trên cùng diarization để
   giảm khác biệt backbone. Cách này vẫn chưa cô lập riêng FDDT hoặc tác động
   fine-tune; không diễn giải thành một ablation kiến trúc hoàn chỉnh.

Thử một số cấu hình decoding trên một subset dev cố định; ghi cả chất lượng,
thời gian và bộ nhớ. Khảo sát lỗi mất lượt ngắn, chia/gộp người nói và lỗi nhận
chữ trên microphone phòng. Tuning bằng dev, đóng băng cấu hình trước khi chấm
test. Các bộ test công khai đã xem kết quả trong lượt này là dữ liệu chẩn đoán,
không dùng lại để tối ưu rồi gọi đó là test chưa đụng tới.

**Đầu ra:** WER/CER, cpWER khi có lời theo người chuẩn; DER theo collar và
overlap policy; miss/false alarm/confusion; lỗi số/tên/phủ định; chênh lệch
ghép cặp theo recording. Báo riêng điều kiện mà mỗi nhánh tốt hoặc kém hơn.

## Mốc 3 — Đo tác dụng của soát sửa, confidence và Kimi

- Hiệu chỉnh confidence trên dev bằng những tín hiệu DiCoW thực sự có.
  Các trường log probability/cluster margin còn thiếu tiếp tục là null.
- So sánh chọn lượt ngẫu nhiên, tín hiệu ASR sẵn có và tín hiệu diarization;
  có thể thử bất đồng giữa hai ASR làm một tín hiệu gợi ý nghe lại.
- Giữ cách tính ngân sách soát theo thời lượng lượt nói. Đo lỗi còn lại khi
  soát 20% ngân sách, đồng thời báo phần speech bị bỏ sót không có turn để flag.
- Chấm Kimi dạng gợi ý trên dev họp thông thường, gồm cả đoạn ASR vốn đúng.
  Đếm lỗi được sửa, lỗi mới, đổi nghĩa, thay số/phủ định và thời gian review.
- Glossary lấy từ agenda/tên/thuật ngữ biết trước của cuộc họp; giữ một nhánh
  không glossary. Đáp án dùng chấm không đi vào prompt.

**Đầu ra:** số liệu chứng minh có tiết kiệm công nghe sửa; calibration/prompt
đóng băng; quyết định rõ phạm vi gợi ý cần người duyệt. Fine-tune chỉ là bước
cân nhắc sau khi có đủ cặp lỗi–chuẩn và bằng chứng lỗi lặp có hệ thống.

## Mốc 4 — Nghiệm thu biên bản, hỏi đáp và luồng sử dụng

Với mỗi cuộc họp, đánh giá hai đầu vào riêng: transcript chuẩn/đã sửa và
transcript ASR gốc. Cách này giúp phân biệt lỗi LLM với lỗi lan truyền từ ASR.

- Chấm ý chính, quyết định, việc cần làm, người phụ trách và thời hạn theo
  tham chiếu có nguồn. Tách đề xuất khỏi quyết định và dùng lời đính chính sau.
- Có câu hỏi có đáp án, không có đáp án, cần nhiều lượt và có thay đổi quyết
  định/thời hạn. Gán nhãn độ đúng, độ đầy đủ và hỗ trợ bởi nguồn; báo coverage.
- Dùng bộ hỏi đáp tiếng Việt để kiểm tra tăng số ứng viên retrieval. Các số
  QMSum chỉ gợi ý hướng thử, không đủ để tự đổi mặc định hoặc kết luận QA tốt.
- Bổ sung mẫu biên bản chung nếu ba mẫu project/standup/customer hiện tại
  không phù hợp một loại cuộc họp trong bộ nghiệm thu.
- Sau khi tác dụng sửa ASR đã được đo, tích hợp gợi ý trước/sau, nghe nguồn,
  chấp nhận/từ chối và lịch sử revision vào web.
- Nghiệm thu upload → nghe/sửa → tạo lại biên bản → hỏi đáp → export trên
  bản ghi thật. Đo thời gian với các bản 5/15/30 phút và ghi rõ cache/device.

**Đầu ra:** bảng chấm semantic và lỗi quan trọng; cấu hình cuối; artifact có
provenance; hướng dẫn tái chạy; một demo hoàn chỉnh trên cuộc họp thông thường.

## Công cụ có thể dùng ngay

- `scripts/evaluate_general_meetings.py`: selection đóng băng, pipeline hiện
  tại, chấm DER/WER/CER/cpWER theo loại nhãn và tổng hợp kết quả.
- `scripts/compare_general_meeting_asr.py`: nhánh PhoWhisper dùng lại M1 và
  timeline DiariZen dự đoán, không đưa nhãn chuẩn vào suy luận.
- `scripts/evaluate_qmsum_retrieval.py`: chẩn đoán retrieval bằng evidence spans.
- Các runner confidence, nghiệm thu semantic và workflow review hiện có
  trong [ACCEPTANCE.md](../ACCEPTANCE.md) tiếp tục được tái sử dụng.

## Quyết định về fine-tuning và vòng cải thiện đầu tiên

**Hiện chưa cần bắt đầu training.** Đối chứng đã có cho thấy WER ViMD giảm
20,82% → 16,54% khi dùng nhánh nhận chữ khác trên cùng timeline DiariZen,
không có lượt training nào trong project. Cần kiểm tra lợi ích đó trên cuộc
họp thật và khảo sát decoding trước khi đầu tư dữ liệu/compute cho fine-tune.

Vòng cải thiện đầu tiên có thể chốt thành các đầu việc sau:

1. Hoàn thành bộ tham chiếu ở mốc 1 và nghe rà ba file ViYT đã đánh dấu.
   Cố định dev/test theo recording, quy ước transcript và phiên bản scorer.
2. Trên dev, đo DiCoW beam 1/3/5 với cùng model, diarization và preprocessing.
   Ghi WER/CER, cpWER và thước đo có ràng buộc thời gian khi đủ nhãn; đo thêm
   thời gian và VRAM. Mỗi cấu hình phải chạy được trong giới hạn GPU thực tế.
3. So nhánh DiariZen + PhoWhisper trên cùng dev; giữ phân nhóm lời rõ, giọng
   khó, microphone phòng và overlap. So cả lỗi chữ lẫn gán lời theo người.
4. Chỉ khảo sát ngưỡng speech/clustering khi các lỗi diarization đã được
   xác nhận bằng audio. Tăng/giảm phát hiện speech có thể đồng thời đổi
   false alarm, miss và chất lượng ASR; chấm cả chuỗi xử lý.
5. Khôi phục canary LLM, đánh giá riêng biên bản trên transcript chuẩn và ASR.
   Kimi tiếp tục là gợi ý cần duyệt; đo lỗi mới và công sửa trước khi tích hợp web.
6. Chọn cấu hình bằng dev, đóng băng và chạy test giữ riêng. So sánh với cấu
   hình ban đầu theo từng recording và công nghe sửa, không chỉ một WER tổng.

Mốc WER 10–15% là định hướng cải thiện ban đầu trên bộ họp đại diện, không
phải mức giảm đã được chứng minh hoặc cam kết đạt bằng thay beam size.

### Khi nào cần fine-tune phần nào?

| Lỗi còn lại sau vòng dev | Hướng cân nhắc | Dữ liệu cần |
|---|---|---|
| Sai chữ lặp theo vùng giọng/điều kiện thu dù diarization đúng | Thích nghi ASR/DiCoW | Audio–transcript đã soát; với DiCoW cần dữ liệu speaker activity phù hợp recipe tác giả |
| Bỏ sót speech, gộp/tách nhầm người có hệ thống | Thích nghi diarization | Recording nhiều người với nhãn speech, speaker và overlap đúng |
| Sai tên/thuật ngữ theo từng cuộc họp | Glossary, context và đối chứng âm thanh trước | Danh sách biết trước có nguồn; patch được người nghe kiểm tra |
| Biên bản sai dù đầu vào transcript đã đúng | Prompt/schema/retrieval và kiểm tra semantic trước | Transcript–đầu ra chuẩn có dẫn chứng; cân nhắc training sau nếu lỗi vẫn lặp |

Nếu chuyển sang training, cần một tập **train riêng**, độc lập với dev/test
đã dùng nghiệm thu. Bộ khoảng một giờ họp ở mốc 1 chủ yếu phục vụ đánh giá;
không mặc định đủ cho training hoặc đồng thời dùng toàn bộ làm cả train và test.

Fine-tune nghĩa là huấn luyện thêm từ checkpoint đang có để thích nghi dữ
liệu mục tiêu, không phải huấn luyện lại từ đầu. Với DiCoW, dùng training code
của tác giả để bảo toàn đầu vào speaker/STNO và FDDT. Việc chỉ mở một phần
tham số hoặc dùng adapter phải được kiểm chứng trên kiến trúc này trước khi
chọn; chưa khẳng định một cách fine-tune cụ thể sẽ vừa GPU local 4 GB.

Trước lượt train dài: chạy một smoke training nhỏ, kiểm tra loss, dữ liệu vào,
bộ nhớ và checkpoint; sau đó thử một pilot thích nghi. Giữ lại bản pretrained
để đối chiếu và chỉ chọn model mới khi có lợi trên dữ liệu giữ riêng. Paper
MLC-SLM cho thấy domain adaptation có thể giúp nhưng cũng ghi nhận tác động
của nhãn không nhất quán:
[BUT System for the MLC-SLM Challenge, §3–4](https://arxiv.org/html/2506.13414v1#S3).
