# ERPCM

ERP mã nguồn mở cho doanh nghiệp Việt Nam. ERPCM là một app [Frappe](https://frappe.io/framework) chạy trên
[ERPNext](https://erpnext.com) v16, thêm những phần doanh nghiệp Việt Nam cần mà ERPNext gốc chưa có.

*ERPCM is an open-source Frappe app that adds Vietnamese localisation to ERPNext v16: tax-code validation, VietQR on
invoices, an e-invoice XML reader, a chart of accounts. GPLv3. Documentation is in Vietnamese. A chart of accounts
modelled on Appendix II of Circular 99/2025/TT-BTC; not verified against the circular text, not certified, no
compliance claim.*

Trang dự án: <https://erpcm.com>

## Bản 0.2.0 có gì

| Phần | Làm gì | Ở đâu |
|---|---|---|
| Kiểm mã số thuế | Từ chối mã số thuế sai số kiểm tra khi lưu Customer / Supplier; chuẩn hoá mã đúng về một cách viết. Hỗ trợ mã 13 số của đơn vị trực thuộc. | `erpcm/vn/taxcode.py`, `erpcm/vn/hooks.py` |
| VietQR trên hoá đơn bán | Hàm Jinja cho mẫu in: mã QR chuyển khoản theo chuẩn NAPAS, đúng tài khoản công ty, số tiền còn phải thu, nội dung là số hoá đơn. | `erpcm/vn/vietqr.py`, `erpcm/vn/hooks.py` |
| Đọc hoá đơn điện tử XML | Đọc tệp XML tải từ cổng thuế thành dict, tự kiểm tổng tiền. Tên thẻ theo cấu trúc công bố của QĐ 1450/QĐ-TCT, **chưa đối chiếu đủ với tệp thật**; mới là thư viện, chưa tạo chứng từ. | `erpcm/vn/xml_invoice.py` |
| Hệ thống tài khoản (Thông tư 99) | Tạo một công ty mới với hệ thống tài khoản này, nhóm tài khoản và tài khoản mặc định, trong một giao dịch. Công ty đã có hệ thống tài khoản thì giữ nguyên. **Chưa đối chiếu với văn bản Thông tư**, xem dưới. | `erpcm/vn/accounting/` |
| Nhóm tài khoản và tài khoản mặc định | Gán Account Category (nhóm báo cáo do ERPCM tự đặt) theo bản chất tài khoản; điền các ô tài khoản mặc định của Company. Làm sẵn khi tạo công ty; gọi lại được để sửa. | `erpcm/vn/accounting/setup.py` |

Phần tính toán là hàm thuần, không cần site hay cơ sở dữ liệu để kiểm.

## Kế toán theo Thông tư 99

**Kế toán theo Thông tư 99/2025/TT-BTC (đang hoàn thiện).** ERPCM kèm một hệ thống tài khoản dựng theo Phụ lục II của Thông tư 99/2025/TT-BTC, cộng một số tài khoản kỹ thuật mà ERPNext cần (liệt kê ở docs/ke-toan-tt99.md). Danh mục do dự án tự nhập, **chưa được đối chiếu từng số hiệu với văn bản Thông tư và chưa được cơ quan hay đơn vị kiểm toán nào thẩm định**. ERPCM không cam kết "tuân thủ Thông tư 99". Kế toán trưởng của doanh nghiệp phải đối chiếu trước khi dùng.

Hệ thống tài khoản gồm 189 tài khoản (153 tài khoản chi tiết, 36 tài khoản tổng hợp); 21 mục bổ sung mà dự án biết
(gốc, nhóm gom, tài khoản kỹ thuật ERPNext cần, và bốn lựa chọn loại tài khoản của ERPNext trên 6428, 811, 141 và
334); 38 nhóm
tài khoản (Account Category); 16 ô tài khoản mặc định của Company.

Cài app **không** đổi hệ thống tài khoản của công ty nào. Người có vai trò System Manager hoặc Accounts Manager tạo
một công ty mới với hệ thống tài khoản này:

```bash
bench --site ten-site execute erpcm.vn.accounting.setup.create_company --kwargs "{'company_name': 'Tên công ty', 'abbr': 'VT'}"
bench --site ten-site execute erpcm.vn.accounting.setup.chart_status --kwargs "{'company': 'Tên công ty'}"
```

`create_company` tạo một công ty Việt Nam mà không để ERPNext dựng hệ thống tài khoản mặc định, rồi trong cùng giao
dịch dựng hệ thống tài khoản này, các kho mặc định, nhóm tài khoản và 16 ô tài khoản mặc định (với Frappe HR, cả các
tài khoản Frappe HR cần); lỗi giữa chừng thì không còn lại gì — với điều kiện ERPCM kiểm trước khi ghi: số lệnh ghi
không thể chạm giới hạn `max_writes_per_transaction` của site. Mọi ô tài khoản mặc định là lựa chọn của dự án mà kế
toán trưởng phải xem lại: bảng ở
[docs/ke-toan-tt99.md](docs/ke-toan-tt99.md#tài-khoản-mặc-định-lựa-chọn-của-dự-án-kế-toán-trưởng-xem-lại). Cài Frappe HR
sau khi đã có công ty TT99 thì chạy `set_company_defaults` cho công ty ấy **trước** mọi lần lưu form Company.

Một công ty đã có hệ thống tài khoản (ví dụ công ty do setup wizard tạo) **giữ nguyên** hệ thống ấy: ERPCM không xoá
hay thay tài khoản của công ty nào. Chi tiết, danh sách tài khoản bổ sung, khác biệt với một công ty do setup wizard
tạo: [docs/ke-toan-tt99.md](docs/ke-toan-tt99.md).

## Cài đặt

Cần một bench chạy Frappe 16 (từ 16.56) và ERPNext 16 (từ 16.55). Đã thử trên ERPNext 16.55 / Frappe 16.56.

```bash
bench get-app https://github.com/erpcm/erpcm
bench --site ten-site install-app erpcm
```

Lúc cài, ERPCM thêm ô **NAPAS BIN** vào danh mục Bank. Điền mã BIN 6 số cho ngân hàng của công ty thì mã VietQR mới
hiện trên mẫu in.

### Dùng VietQR trong mẫu in

```jinja
{% set qr = vietqr_svg_for_sales_invoice(doc.name) %}
{% if qr %}<img src="{{ qr }}" width="140" height="140" alt="VietQR">{% endif %}
```

Hàm trả `None` khi hoá đơn không phải VND, hoặc công ty chưa có tài khoản ngân hàng mặc định kèm NAPAS BIN. Nó
không bao giờ ném lỗi, để mẫu in không hỏng vì thiếu mã QR.

## Chạy test

```bash
pip install pytest
python -m pytest -q
```

Bộ test trong `tests/` không cần site, cơ sở dữ liệu hay mạng. Cần Python 3.10 trở lên.

## Lộ trình

Xem [docs/ROADMAP.md](docs/ROADMAP.md). Các phần đang được chuyển dần từ một hệ thống ERPNext đang chạy thật; mỗi
phần chỉ vào đây sau khi đã gỡ hết cấu hình riêng và có test.

## Đóng góp

Báo lỗi và đề xuất qua GitHub Issues. Với mã nguồn: mỗi thay đổi kèm test đỏ khi bỏ phần sửa; phần tính toán viết
thành hàm thuần, tách khỏi phần chạm vào chứng từ Frappe.

## Giấy phép

GNU General Public License v3.0, xem [LICENSE](LICENSE).

ERPNext và Frappe là nhãn hiệu của Frappe Technologies Pvt. Ltd. ERPCM là dự án độc lập, không thuộc và không được
Frappe bảo trợ.
