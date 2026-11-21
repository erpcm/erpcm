# Lộ trình

Chưa có ngày hẹn. Thứ tự có thể đổi theo góp ý của người dùng. Một phần chỉ được đưa vào khi: đã gỡ hết cấu hình
riêng của nơi nó đang chạy, có test không cần site, và đã cài thử trên một bench sạch.

## Đã có

0.1.0:

- Kiểm mã số thuế trên Customer / Supplier.
- VietQR cho Sales Invoice (hàm Jinja cho mẫu in).
- Đọc hoá đơn điện tử XML (thư viện; tên thẻ chưa đối chiếu đủ với tệp thật).

0.2.0:

- Hệ thống tài khoản dựng theo Phụ lục II của Thông tư 99/2025/TT-BTC, **chưa đối chiếu với văn bản Thông tư**
  ([ke-toan-tt99.md](ke-toan-tt99.md)): tạo một công ty mới với hệ thống tài khoản này, nhóm tài khoản và tài khoản mặc
  định, trong một giao dịch. Công ty đã có hệ thống tài khoản thì giữ nguyên.
- Nhóm tài khoản (Account Category, do dự án tự đặt) theo bản chất tài khoản; tài khoản mặc định của Company.

## Đã thử trên bench sạch (21/11/2026)

0.1.0 — Frappe 16.56.0 + ERPNext v16.55.0, site mới: `bench get-app` từ GitHub, `install-app erpcm`, ô NAPAS BIN có
trên Bank, lưu Supplier với mã số thuế sai bị từ chối và mã đúng được chuẩn hoá, cài lại lần hai không đổi gì.

0.2.0 — cùng phiên bản Frappe / ERPNext, MariaDB 11.8, site mới, chạy bằng `tools/bench/proof.sh` (app cài từ cây mã
cục bộ: chép vào bench, `pip install -e`, thêm vào `apps.txt`, `install-app`; chưa từ GitHub), hai lượt: có Frappe HR
v16.54.1 (commit `a0103235`) cài trước setup wizard — 93 điều phải đúng, 0 sai — và `HRMS=0`, Frappe HR chỉ cài ở
cuối, sau khi đã có các công ty — 89 điều phải đúng, 0 sai. Kịch bản đòi đúng số điều ấy.

- Công ty do setup wizard tạo (Việt Nam, VND, "Standard"): 96 tài khoản với Frappe HR, 95 không có. `install-app erpcm`
  không đổi gì (cùng dấu băm trước và sau); `chart_status` `DIFFERENT`; `setup_chart` `DIFFERENT`, hai thao tác sửa lại
  từ chối; cuối lượt công ty này vẫn đúng dấu băm ban đầu.
- Ép lỗi sau khi đã dựng hệ thống tài khoản, 5 kho và 38 nhóm tài khoản, lúc site chưa có nhóm nào của ERPCM (một lần
  `RuntimeError`, một lần `KeyboardInterrupt`), bên gọi vẫn commit: một tiến trình mới không thấy Company, tài khoản, kho,
  cost center, phòng ban, dòng Mode of Payment hay dòng Expense Claim nào của công ty ấy, số Account Category như cũ,
  không khoá cache nào mang tên hay viết tắt của nó; cờ `ignore_chart_of_accounts` trở về như cũ.
- Một nhóm tài khoản cơ sở dữ liệu coi là cùng tên ("PHẢI TRẢ NGƯỜI BÁN") nhưng khác `root_type`: từ chối, không tạo
  gì. Một nhóm cùng tên khác hoa thường, cùng `root_type` ("tiền và tương đương tiền"): được dùng lại.
- `create_company('Cong Ty TT99', 'TT99')`: 189 tài khoản, 5 kho, cost center `Main - TT99`, 37 nhóm tạo mới (1 dùng
  lại), 16 ô tài khoản mặc định (18 với Frappe HR: thêm 334, 141); với Frappe HR, một dòng Expense Claim trên 6428 cho
  mỗi trong 5 Expense Claim Type, dòng của công ty khác không đổi (so từng dòng); `chart_status` `MATCH` kiểu `vi_en`
  (cùng qua `bench execute`). Lưu form Company sau đó: không thêm tài khoản nào, vẫn `MATCH`.
- Từ chối, số công ty không đổi: cùng tên, tên viết hoa, cùng viết tắt, viết tắt khác hoa thường, viết tắt 11 ký tự (tên
  song ngữ 142 ký tự; với `names="vi"` thì tạo được), viết tắt "A B" / "A%" / "A-B", tên công ty 136 ký tự (cost center
  gốc 141 ký tự); một lệnh ghi chưa commit trong giao dịch; điều khiển giao dịch bị tắt; `max_writes_per_transaction` hạ
  xuống 1.500.
- So với công ty của wizard: kho, cost center, phòng ban, dòng Mode of Payment, dòng Expense Claim giống nhau; mọi ô
  tài khoản wizard điền thì công ty TT99 cũng có; các trường còn lại của Company chỉ khác `domain`; wizard có 3 mẫu
  thuế "Vietnam Tax", công ty TT99 không có.
- Ngoài công ty mới, một lần `create_company` sửa đúng: đồng tiền VND, Mode of Payment "Cash", Property Setter
  `Purchase Receipt-provisional_expense_account-hidden`, và với Frappe HR, mọi Expense Claim Type; không thêm Property
  Setter nào.
- Công ty chưa có tài khoản nào: `setup_chart` dựng 189 tài khoản (không tạo kho); hai thao tác sửa lại áp được; lần hai
  cả ba `MATCH`.
- HTTP: GET `chart_status` 200, 403 với công ty không có; GET bốn thao tác ghi 403; POST `create_company` tạo được, tham
  số `country="Italy"` bị bỏ qua, công ty là Việt Nam.
- Trên công ty TT99: Purchase Receipt (156 / 3389), Purchase Invoice (3389 / 331), Sales Invoice (131 / 511), Payment
  Entry (112 / 131), Stock Entry nhập (156 / 811) và xuất (811 / 156) kho, một Payment Entry xoá nợ 10.000 qua khấu
  trừ (811); với Frappe HR, một Employee Advance trên 141 được trả (trạng thái Paid) và bước kiểm tài khoản lương phải
  trả của Payroll Entry (trước khi submit) qua được với 334 — chưa chạy một kỳ lương đủ. Stock Closing Entry rồi Period
  Closing Voucher đến 30/06/2026: lãi lỗ về 0, 440.000 nằm lại trên 911. Sau đó `chart_status` và `setup_chart` `MATCH`,
  nhóm tài khoản từ chối, `set_company_defaults` từ chối (không Frappe HR) hay không còn gì để điền (có Frappe HR), không
  đổi gì.
- Người chỉ có Accounts User: 403 ở cả năm thao tác; Accounts Manager tạo được công ty.
- `names="vi"`: `MATCH` kiểu `vi`. `innodb_snapshot_isolation=OFF`: tạo được, `MATCH` (một tiến trình; không thử đụng độ
  với tài khoản đang được thêm ở công ty khác).
- Frappe HR cài sau khi đã có các công ty (`HRMS=0`): lưu form Company của một công ty TT99 trước khi chạy
  `set_company_defaults` thì Frappe HR thêm "Expense Claims" và `chart_status` thành `DIFFERENT` (đúng như tài liệu
  cảnh báo); trên công ty TT99 đã có bút toán, `set_company_defaults` chỉ điền 334, 141 và 5 dòng Expense Claim, sau đó
  lưu form Company không thêm tài khoản nào, vẫn `MATCH`.

## Còn phải thử

- Mẫu in Sales Invoice có VietQR trên một công ty đã có tài khoản ngân hàng.
- Đối chiếu hệ thống tài khoản với văn bản Phụ lục II (cần `tt99_appendix_ii.json` do người chép).
- Trên hệ thống tài khoản mới: mua tài sản cố định (3385), khấu hao, Landed Cost Voucher, nhập số dư đầu kỳ qua 1385,
  Sales Invoice có cập nhật kho (giá vốn 632), mẫu thuế GTGT trên 1331 / 3331.
- Cài từ GitHub sau khi nhánh được gộp.

## Dự kiến

| Phần | Nội dung |
|---|---|
| Kế toán Việt Nam | Báo cáo tài chính theo chế độ kế toán doanh nghiệp (Thông tư 99) trên các nhóm tài khoản của 0.2.0, cột so sánh kỳ trước, mẫu thuế GTGT, bảng kê hoá đơn mua vào, checklist đóng kỳ. |
| Phát hành hoá đơn điện tử | Phát hành từ Sales Invoice qua nhà cung cấp hoá đơn điện tử; kiểm trước dữ liệu khách hàng; hoá đơn điều chỉnh và thay thế theo Nghị định 70/2025. |
| Số chứng từ theo pháp nhân | Mỗi công ty một dải số riêng cho từng loại chứng từ. |
| Giao diện tiếng Việt | Bản dịch bổ sung và mẫu in chứng từ theo cách trình bày quen dùng ở Việt Nam. |
