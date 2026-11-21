# ERPCM

ERP mã nguồn mở cho doanh nghiệp Việt Nam. ERPCM là một app [Frappe](https://frappe.io/framework) chạy trên
[ERPNext](https://erpnext.com) v16, thêm những phần doanh nghiệp Việt Nam cần mà ERPNext gốc chưa có.

*ERPCM is an open-source Frappe app that adds Vietnamese localisation to ERPNext v16: tax-code validation, VietQR on
invoices, an e-invoice XML reader. GPLv3. Documentation is in Vietnamese.*

Trang dự án: <https://erpcm.com>

## Bản 0.1.0 có gì

| Phần | Làm gì | Ở đâu |
|---|---|---|
| Kiểm mã số thuế | Từ chối mã số thuế sai số kiểm tra khi lưu Customer / Supplier; chuẩn hoá mã đúng về một cách viết. Hỗ trợ mã 13 số của đơn vị trực thuộc. | `erpcm/vn/taxcode.py`, `erpcm/vn/hooks.py` |
| VietQR trên hoá đơn bán | Hàm Jinja cho mẫu in: mã QR chuyển khoản theo chuẩn NAPAS, đúng tài khoản công ty, số tiền còn phải thu, nội dung là số hoá đơn. | `erpcm/vn/vietqr.py`, `erpcm/vn/hooks.py` |
| Đọc hoá đơn điện tử XML | Đọc tệp XML tải từ cổng thuế thành dict, tự kiểm tổng tiền. Tên thẻ theo cấu trúc công bố của QĐ 1450/QĐ-TCT, **chưa đối chiếu đủ với tệp thật**; mới là thư viện, chưa tạo chứng từ. | `erpcm/vn/xml_invoice.py` |

Phần tính toán là hàm thuần, không cần site hay cơ sở dữ liệu để kiểm.

## Cài đặt

Cần một bench chạy Frappe và ERPNext phiên bản 16.

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
