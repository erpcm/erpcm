# Lộ trình

Chưa có ngày hẹn. Thứ tự có thể đổi theo góp ý của người dùng. Một phần chỉ được đưa vào khi: đã gỡ hết cấu hình
riêng của nơi nó đang chạy, có test không cần site, và đã cài thử trên một bench sạch.

## Đã có (0.1.0)

- Kiểm mã số thuế trên Customer / Supplier.
- VietQR cho Sales Invoice (hàm Jinja cho mẫu in).
- Đọc hoá đơn điện tử XML (thư viện; tên thẻ chưa đối chiếu đủ với tệp thật).

## Việc trước khi công bố 0.1.0

- Cài thử `bench get-app` + `install-app` trên một bench Frappe/ERPNext v16 sạch.
- Thử lưu Customer với mã số thuế sai và đúng; thử mẫu in có VietQR.

## Dự kiến

| Phần | Nội dung |
|---|---|
| Kế toán Việt Nam | Hệ thống tài khoản và báo cáo tài chính theo chế độ kế toán doanh nghiệp (Thông tư 99), cột so sánh kỳ trước, bảng kê hoá đơn mua vào, checklist đóng kỳ. |
| Phát hành hoá đơn điện tử | Phát hành từ Sales Invoice qua nhà cung cấp hoá đơn điện tử; kiểm trước dữ liệu khách hàng; hoá đơn điều chỉnh và thay thế theo Nghị định 70/2025. |
| Số chứng từ theo pháp nhân | Mỗi công ty một dải số riêng cho từng loại chứng từ. |
| Giao diện tiếng Việt | Bản dịch bổ sung và mẫu in chứng từ theo cách trình bày quen dùng ở Việt Nam. |
