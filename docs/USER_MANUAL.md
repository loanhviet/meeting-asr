# Hướng dẫn người dùng

Tài liệu liên quan: [Thiết kế giao diện](UI_DESIGN.md), [Quyền riêng tư](DATA_PRIVACY.md).

## Tạo và xử lý cuộc họp

1. Mở website và chọn **Tải bản ghi** (hoặc kéo thả file).
2. Chọn file WAV, MP3 hoặc M4A, tối đa 200 MiB. Hệ thống tạo một công việc xử lý.
3. Theo dõi trạng thái ở danh sách **Cuộc họp** (nút **Thư viện** để quay lại): chuẩn bị bản ghi, phân biệt người nói, chép lời, sắp xếp lượt, chọn đoạn cần nghe lại. Giao diện hiển thị ETA ước tính dựa trên tốc độ xử lý các job đã hoàn tất; thời gian có thể thay đổi. Khi xong, ứng dụng thông báo.
4. Mở cuộc họp để xem transcript, biên bản và danh sách việc. Nếu xử lý lỗi, màn hình hiện thông báo lỗi và nút **Thử lại** để xếp lại job.

## Soát transcript và người nói

5. Trong workspace, phát audio hoặc chọn lượt nói để nghe đúng đoạn. Lượt cần soát được gom ở **Soát ngay →** trong phần biên bản.
6. Sửa nội dung lượt nói, chọn speaker đúng và đánh dấu đã nghe; lưu thay đổi. Phím tắt ở workspace: Space phát/tạm dừng, J/L lùi/tiến 5 giây, R bật/tắt lặp lượt. Trong màn hình soát: Enter xác nhận đúng, E sửa, ↓ bỏ qua, Space nghe đoạn, Ctrl/⌘+Enter lưu bản sửa. Phím tắt không chạy khi đang nhập liệu.
7. Mở **Người nói** để đổi tên hiển thị hoặc gộp nhóm của cùng một người.
8. Có thể thêm tên cuộc họp và người tham dự. Người tham dự là thông tin do người dùng nhập, không phải kết quả nhận dạng.

## Biên bản, việc cần làm và xuất

9. Nếu LLM đã được bật trên máy chủ, chọn mẫu (họp dự án, standup hoặc họp khách hàng) rồi tạo/tạo lại biên bản. Kiểm tra quyết định, việc cần làm, người phụ trách và nguồn dẫn tới lượt nói; nguồn có thể cần nghe lại.
10. Sửa người phụ trách, hạn hoặc trạng thái hoàn thành của việc nếu cần. Khi transcript/người nói đổi, biên bản cũ có thể bị đánh dấu cần tạo lại.
11. Dùng menu **Xuất** để tải Markdown, PDF hoặc phụ đề SRT; chọn **Sao chép danh sách việc** để copy vào clipboard. Có thể chốt biên bản trong workspace.

TODO: ảnh minh hoạ cho tải file, soát lượt và xuất.
