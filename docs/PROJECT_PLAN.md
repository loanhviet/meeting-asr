# Kế hoạch dự án

Các mốc dưới đây lấy từ Git history hiện có (PR merge #1–#5). Không suy ra ngày hoặc mức hoàn thành ngoài commit. Hướng dẫn sử dụng: [USER_MANUAL.md](USER_MANUAL.md); luồng UI: [UI_DESIGN.md](UI_DESIGN.md); rủi ro dữ liệu: [DATA_PRIVACY.md](DATA_PRIVACY.md).

## Mốc đã có trong Git

| Giai đoạn | PR / nhánh | Nội dung theo commit |
|---|---|---|
| 1. Evidence review workspace | #1 `feat/evidence-review-workspace` | Nền tảng review transcript và biên bản có dẫn chứng. |
| 2. DiCoW author pipeline | #2 `feat/dicow-author-pipeline` | Tích hợp pipeline DiariZen + DiCoW, runtime/checkpoint được pin. |
| 3. Sửa chất lượng họp | #3 `feat/meeting-quality-fixes` | Sửa vòng lặp decode và giữ cờ review trên lỗi thật; thêm AskMeeting trả lời theo transcript. |
| 4. UI redesign | #4 `feat/ui-redesign` | Workspace ưu tiên biên bản, tiêu đề meeting, finalize, sửa action item và overview thư viện. |
| 5. Participants và ETA | #5 `feat/participants-eta-notify` | ETA dựa trên tốc độ job đã xong, người tham dự, thông báo hoàn thành và copy action list. |

Git có các nhánh feature tương ứng; nhánh hiện tại `loanhviet/check-git-sync-status` ở commit merge #5. Commit history không xác nhận triển khai production.

## Mốc tiếp theo

| Mốc | Trạng thái |
|---|---|
| Nghiệm thu chất lượng trên cuộc họp thật với transcript/speaker reference đã nghe duyệt | TODO |
| Đánh giá riêng WER/cpWER/DER trên tập dev/test phù hợp | TODO |
| Hoàn tất thiết kế retention, xóa dữ liệu và xác thực nếu triển khai nhiều người dùng | TODO |
| Chốt kế hoạch dữ liệu có giấy phép và điều kiện dùng cho nghiên cứu/huấn luyện | TODO |

## Sổ đăng ký rủi ro

| Rủi ro có căn cứ trong repo | Tác động | Giảm thiểu / việc cần làm |
|---|---|---|
| Chất lượng model chưa được nghiệm thu trên dữ liệu họp thật độc lập | Transcript/speaker attribution có thể sai | Nghe duyệt reference và đánh giá trên split phù hợp; tránh khẳng định tổng quát từ pilot. |
| GPU memory/runtime phụ thuộc model, thiết bị và audio | Xử lý có thể chậm hoặc không chạy trên máy cấu hình thấp | DiCoW decode target tuần tự; kiểm tra runtime/thiết bị trên môi trường triển khai. |
| Audio/transcript nhạy cảm và retention chưa định nghĩa | Lộ hoặc lưu dữ liệu lâu hơn dự kiến | LLM tắt mặc định; chốt quyền truy cập, thời hạn lưu và xóa. |
| Endpoint LLM ngoài nhận nội dung khi bật | Rủi ro theo chính sách nhà cung cấp | Xác minh provider/URL/điều khoản; chỉ bật có chủ đích. |
| Giấy phép/nguồn dữ liệu, checkpoint và runtime upstream | Có thể giới hạn tái sử dụng hoặc phân phối | TODO: lập inventory giấy phép và điều khoản cho từng dataset/model trước khi phát hành. |
| Một worker và chưa có xác thực/ownership đa người dùng | Không đáp ứng triển khai nhiều người dùng | Giữ phạm vi demo local hoặc thiết kế ownership, xác thực, điều phối trước khi mở rộng. |
| ETA lấy tốc độ từ job hoàn tất | Ước lượng có thể lệch ở phần cứng/model khác | Hiển thị là ước tính; thu thập số đo theo môi trường triển khai. |
