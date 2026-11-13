# Hướng dẫn người dùng

Tài liệu liên quan: [Thiết kế giao diện](UI_DESIGN.md), [Quyền riêng tư](DATA_PRIVACY.md).

## Tạo và xử lý cuộc họp

1. Mở website và chọn **Tải bản ghi** (hoặc kéo thả file).
2. Chọn file WAV, MP3 hoặc M4A, tối đa 200 MB. Hệ thống tạo một công việc xử lý.
3. Theo dõi trạng thái ở Thư viện: chuẩn bị bản ghi, phân biệt người nói, chép lời, sắp xếp lượt, chọn đoạn cần nghe lại. Giao diện hiển thị ETA ước tính dựa trên tốc độ xử lý các job đã hoàn tất; thời gian có thể thay đổi. Khi xong, ứng dụng thông báo.
4. Mở cuộc họp để xem transcript, biên bản và danh sách việc. Nếu có lỗi, xem trạng thái job trong Thư viện. **TODO: hướng dẫn thao tác retry nếu có giao diện retry.**

## Soát transcript và người nói

5. Trong workspace, phát audio hoặc chọn lượt nói để nghe đúng đoạn. Lượt được đánh dấu cần soát có thể mở trong màn hình Soát.
6. Sửa nội dung lượt nói, chọn speaker đúng và đánh dấu đã nghe; lưu thay đổi. Có thể dùng Space phát/tạm dừng, J/L lùi/tiến 5 giây, N tới lượt cần soát, R lặp lượt; phím tắt không chạy khi đang nhập liệu.
7. Mở **Người nói** để đổi tên hiển thị hoặc gộp nhóm của cùng một người.
8. Có thể thêm tên cuộc họp và người tham dự. Người tham dự là thông tin do người dùng nhập, không phải kết quả nhận dạng.

## Biên bản, việc cần làm và xuất

9. Nếu LLM đã được bật trên máy chủ, chọn mẫu (họp dự án, standup hoặc họp khách hàng) rồi tạo/tạo lại biên bản. Kiểm tra quyết định, việc cần làm, người phụ trách và nguồn dẫn tới lượt nói; nguồn có thể cần nghe lại.
10. Sửa người phụ trách, hạn hoặc trạng thái hoàn thành của việc nếu cần. Khi transcript/người nói đổi, biên bản cũ có thể bị đánh dấu cần tạo lại.
11. Dùng menu **Xuất** để tải Markdown, PDF hoặc phụ đề SRT; chọn **Sao chép danh sách việc** để copy vào clipboard. Có thể chốt biên bản trong workspace.

TODO: ảnh minh hoạ cho tải file, soát lượt và xuất.
