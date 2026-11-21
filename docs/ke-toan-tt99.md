# Hệ thống tài khoản theo Thông tư 99/2025/TT-BTC

> **Kế toán theo Thông tư 99/2025/TT-BTC (đang hoàn thiện).** ERPCM kèm một hệ thống tài khoản dựng theo Phụ lục II của Thông tư 99/2025/TT-BTC, cộng một số tài khoản kỹ thuật mà ERPNext cần (liệt kê dưới đây). Danh mục do dự án tự nhập, **chưa được đối chiếu từng số hiệu với văn bản Thông tư và chưa được cơ quan hay đơn vị kiểm toán nào thẩm định**. ERPCM không cam kết "tuân thủ Thông tư 99". Kế toán trưởng của doanh nghiệp phải đối chiếu trước khi dùng.

*A chart of accounts modelled on Appendix II of Circular 99/2025/TT-BTC; not verified against the circular text, not
certified, no compliance claim.*

## Có gì

| Tệp | Nội dung |
|---|---|
| `erpcm/vn/accounting/data/tt99_chart.json` | Cây tài khoản theo đúng dạng `create_charts(company, custom_chart=...)` của ERPNext đọc, kèm danh sách `additions`. |
| `erpcm/vn/accounting/data/tt99_categories.json` | Các nhóm tài khoản (Account Category) do dự án tự đặt, và tiền tố số hiệu của từng nhóm. |
| `erpcm/vn/accounting/data/tt99_company_defaults.json` | Ô tài khoản mặc định của Company → số hiệu tài khoản. |
| `erpcm/vn/accounting/chart.py`, `categories.py`, `plan.py` | Hàm thuần: đọc, kiểm, so sánh, quyết định. Không cần site. |
| `erpcm/vn/accounting/setup.py` | Các thao tác chạy trên site: tạo công ty mới với hệ thống TT99, xem, dựng trên công ty chưa có tài khoản, sửa lại. |
| `tools/bench/` | Bench thử dùng một lần và kịch bản chạy lại toàn bộ phần thử trên site. |

Tên tài khoản viết hai thứ tiếng, "Tiếng Việt / English". Nửa tiếng Anh là bản dịch của dự án, không phải văn bản
Thông tư. Muốn chỉ tên tiếng Việt thì dựng với `names="vi"`.

`account_type` (Cash, Bank, Receivable, Stock, Tax…) là thuộc tính của ERPNext, không phải của Thông tư; nó quyết định
cách ERPNext ghi sổ. Các loại được gán là lựa chọn của dự án.

## Những bổ sung dự án biết

Các mục dưới đây là những gì dự án biết là không thuộc Thông tư, hoặc là lựa chọn loại tài khoản của ERPNext mà dự án gán; chúng nằm trong `additions` của `tt99_chart.json`,
và test kiểm từng mục có thật trong cây. Danh sách này chưa được đối chiếu với văn bản, nên có thể chưa đủ.

| Số hiệu | Tài khoản | Vì sao có |
|---|---|---|
| — | Năm gốc: Tài sản, Nợ phải trả, Vốn chủ sở hữu, Doanh thu và thu nhập, Chi phí | ERPNext bắt buộc mỗi gốc mang một `root_type`. |
| 9 | Xác định kết quả kinh doanh (gốc, `root_type` Equity) | Period Closing Voucher chỉ nhận tài khoản kết chuyển thuộc Equity hoặc Liability, nên 911 phải nằm dưới một gốc Equity. |
| 1, 2, 5, 6, 7, 8 | Nhóm một chữ số | Dự án thêm để gom các tài khoản cùng loại. Không có nhóm 3 hay 4: tài khoản loại 3, 4 nằm thẳng dưới gốc. |
| 1385 | Số dư đầu kỳ tạm | Tài khoản loại Temporary làm đối ứng khi nhập số dư đầu kỳ. |
| 3389 | Hàng nhận chưa có hoá đơn | ERPNext bắt buộc khi bật kế toán kho kê khai thường xuyên. |
| 3385 | Tài sản nhận chưa có hoá đơn | ERPNext dùng khi mua tài sản cố định. |
| — | Chi phí mua hàng phân bổ vào giá trị tồn kho | Tài khoản kỹ thuật cho Landed Cost Voucher. |
| — | Chi phí phân bổ vào giá trị tài sản | Tài khoản kỹ thuật tương ứng cho tài sản. |
| 6428 | Chi phí bằng tiền khác, mang loại Round Off | 6428 có trong danh mục dự án dựng theo Thông tư (chưa đối chiếu); gán loại Round Off cho nó là lựa chọn của dự án. |
| 141 | Tạm ứng, mang loại Receivable | Frappe HR đòi tài khoản tạm ứng nhân viên mang loại Receivable. Hệ quả: ERPNext đòi ghi đối tượng (Employee) trên mọi dòng Journal Entry vào 141. Lựa chọn của dự án; kế toán trưởng xem lại. |
| 334 | Phải trả người lao động, mang loại Payable | Frappe HR đòi tài khoản lương phải trả mang loại Payable (Payroll Entry kiểm trước khi submit). Hệ quả: ERPNext đòi ghi đối tượng (Employee) trên mọi dòng Journal Entry vào 334. Lựa chọn của dự án; kế toán trưởng xem lại. |
| 811 | Chi phí khác, mang loại Stock Adjustment | 811 có trong danh mục (chưa đối chiếu); ERPNext đòi một tài khoản loại Stock Adjustment cho ô `stock_adjustment_account`, và gán loại ấy cho 811 là lựa chọn của dự án. Kế toán trưởng xem lại. |

### Cần đối chiếu với Thông tư

- 1385, 3385, 3389: số hiệu do dự án chọn; **chưa kiểm** Thông tư có dùng các số này cho tài khoản khác hay không.
- 3525 "Dự phòng phải trả khác": số hiệu này cần được kiểm riêng với văn bản.
- Toàn bộ danh mục còn lại, xem mục cuối.

## Chạy thế nào

Không có gì chạy lúc `install-app` hay `migrate`. Người có vai trò System Manager hoặc Accounts Manager tự gọi.

### Tạo công ty mới với hệ thống TT99: `create_company`

```bash
bench --site ten-site execute erpcm.vn.accounting.setup.create_company --kwargs "{'company_name': 'Tên công ty', 'abbr': 'VT'}"
```

Cũng gọi được qua API bằng POST (`/api/method/erpcm.vn.accounting.setup.create_company`). Cần quyền tạo Company.
Tham số: `company_name`, `abbr` (chỉ chữ và số), `default_currency="VND"`, `names="vi_en"` (hay `"vi"`: tên chỉ tiếng
Việt). Công ty luôn là công ty Việt Nam: hệ thống tài khoản là của Việt Nam, và với vài quốc gia khác bước thiết lập
theo quốc gia của ERPNext tự commit giữa chừng.

Trong **một giao dịch**: tạo Company với cờ `ignore_chart_of_accounts` của ERPNext bật, để ERPNext không dựng hệ thống
tài khoản mặc định của nó; dựng hệ thống TT99 bằng `create_charts`; cài các mẫu báo cáo tài chính ERPNext cài cho một
công ty mới; tạo các kho mặc định (All Warehouses, Stores, Work In Progress, Finished Goods, Goods In Transit); gán
nhóm tài khoản; điền 16 ô tài khoản mặc định và dòng tài khoản của Mode of Payment "Cash". Cost center và phòng ban mặc
định do ERPNext tạo như với mọi công ty. Khi site có Frappe HR: điền thêm `default_payroll_payable_account` (334) và
`default_employee_advance_account` (141), và cho mỗi Expense Claim Type một dòng tài khoản **của công ty này** trỏ vào
6428 — có sẵn những thứ ấy thì khi Company được lưu về sau, Frappe HR không tự tạo tài khoản "Expense Claims" ngoài hệ
thống TT99. Dòng của các công ty khác không bị đụng. Một Expense Claim Type tạo **sau** đó thì chưa có dòng cho công ty
này: thêm dòng ấy trước lần lưu Company kế tiếp, nếu không Frappe HR sẽ tạo tài khoản "Expense Claims". Trên một site
mà Expense Claim Type có một trường tự thêm bắt buộc, `create_company` không chạy được (rollback sạch; lần lưu Company
của chính Frappe HR cũng hỏng như vậy).

> **Cài Frappe HR sau khi đã có công ty TT99:** chạy `set_company_defaults` cho từng công ty TT99 **trước** mọi lần lưu
> form Company. Lưu trước thì Frappe HR tạo tài khoản "Expense Claims" ngoài hệ thống TT99 và `chart_status` thành
> `DIFFERENT` (đã thấy trên bench). Với công ty đã có bút toán, `set_company_defaults` vẫn chạy cho phần này: nó chỉ điền
> các ô trống của Frappe HR và thêm dòng Expense Claim của công ty, không đổi ô mặc định nào khác, và kết quả nói rõ đã
> điền gì.

Lỗi ở bất cứ bước nào (kể cả Ctrl-C) thì không còn lại gì: không Company, không tài khoản, không kho, không dòng Mode of
Payment hay Expense Claim, không nhóm tài khoản mới, và cache được xoá trước khi rollback. Lời hứa ấy dựa trên một điều
kiện ERPCM kiểm trước khi ghi: số lệnh ghi có thể cần (số tài khoản trên cả site × 2 + 1.000) phải dưới giới hạn lệnh
ghi một giao dịch của site (`max_writes_per_transaction`, mặc định 200.000), vì quá giới hạn ấy `rebuild_tree` của
ERPNext tự commit giữa chừng. Không đạt thì từ chối.

Từ chối, không ghi gì, khi: đã có công ty cùng tên (không phân biệt hoa thường hay dấu, như cơ sở dữ liệu so — nhưng "đ" khác "d") hay cùng viết tắt; viết tắt có ký
tự không phải chữ hay số; tên cost center gốc (`tên công ty - viết tắt`) hay tên tài khoản dài nhất (số hiệu - tên -
viết tắt) vượt 140 ký tự ERPNext cho phép — tên song ngữ chỉ chừa khoảng 9 ký tự cho viết tắt, dùng `names="vi"` hoặc
viết tắt ngắn hơn; số lệnh ghi có thể chạm giới hạn (trên); một nhóm tài khoản mà cơ sở dữ liệu coi là cùng tên (khác
hoa thường hay dấu cũng vậy) đã có với `root_type` khác — cùng `root_type` thì dùng lại nhóm ấy; bản ERPNext thiếu trường
`root_type` trên Account Category. Kiểm quyền tạo Company trước mọi kiểm tra trên, nên lời từ chối "đã có công ty" chỉ
đến người có quyền tạo công ty.

Ngoài công ty mới, một lần `create_company` thành công còn ghi những thứ dùng chung của site (thấy trên bench, xem
docs/ROADMAP.md): Property Setter `Purchase Receipt-provisional_expense_account-hidden` do ERPNext đặt khi lưu
Company; ngày sửa (`modified`) của đồng tiền VND và của Mode of Payment "Cash" (thêm dòng cho công ty mới); các mẫu báo
cáo tài chính và nhóm IFRS chuẩn của ERPNext nếu chúng đã bị xoá thì được cài lại; với Frappe HR, các Expense Claim
Type được thêm dòng của công ty mới.

So với một công ty do setup wizard tạo (đã so trên bench, docs/ROADMAP.md), công ty tạo bằng `create_company` khác ở:
hệ thống tài khoản; không có mẫu thuế "Vietnam Tax" (mẫu thuế ấy của ERPNext dựng trên tài khoản VAT của hệ thống tài
khoản mặc định; hãy tạo mẫu thuế trên 1331 / 3331); ô `domain` để trống. Kho, cost center, phòng ban, dòng Mode of
Payment, dòng Expense Claim (với Frappe HR) giống nhau, và mọi ô tài khoản mặc định wizard điền thì công ty TT99 cũng
có. Ô `chart_of_accounts` của Company vẫn ghi "Standard" như ERPNext tự điền; nó không nói gì về hệ thống tài khoản
thật của công ty.

**Đừng bấm "Create Tax Template" trên form Company** của công ty TT99: nút ấy chạy bước thiết lập thuế của ERPNext, tạo
nhóm "Duties and Taxes" và tài khoản "VAT" ngoài hệ thống TT99 (khi đó `chart_status` thành `DIFFERENT`).

Một công ty đã có hệ thống tài khoản thì **giữ nguyên** hệ thống ấy. ERPCM không xoá, không thay tài khoản của công
ty nào: trên một site ERPNext đang chạy, việc ấy không làm an toàn được từ bên trong một app — ERPNext ghi sổ mà không
khoá Company hay Account, nên một request đã đọc tài khoản trước lúc thay vẫn có thể ghi vào nó sau đó. Chuyển dữ liệu
từ một công ty cũ sang công ty mới là quyết định của người quản trị, làm bằng công cụ của ERPNext.

### `chart_status(company, names="vi_en")`

Chỉ đọc, gọi được bằng GET. Trả `verdict`:

| verdict | Nghĩa |
|---|---|
| `MATCH` | Tài khoản của công ty đúng như tệp, ở một trong hai kiểu tên (`style` nói kiểu nào). |
| `BUILD` | Công ty chưa có tài khoản nào: `setup_chart` dựng được. |
| `DIFFERENT` | Công ty có hệ thống tài khoản khác. ERPCM không thay nó; dùng `create_company`. |

Công ty không có, hay người gọi không có quyền đọc nó, đều nhận cùng một lỗi 403.

### `setup_chart(company, names="vi_en")`

Chỉ dựng hệ thống TT99 trên một công ty **chưa có tài khoản nào** (ví dụ công ty nhập dữ liệu vào với cờ
`ignore_chart_of_accounts`). Mọi trường hợp khác trả `chart_status` và không ghi gì. Nó chỉ dựng tài khoản: **không tạo
kho**, không gán nhóm, không điền ô mặc định. Sau đó chạy hai thao tác dưới, và tạo kho bằng ERPNext.

### `apply_account_categories(company)` và `set_company_defaults(company)`

Hai thao tác sửa lại, cho công ty đã có hệ thống TT99 (`chart_status` là `MATCH`) và chưa có bút toán; không thì từ
chối và không ghi gì. Chúng chỉ đổi Account Category của tài khoản công ty ấy và các ô tài khoản trên Company ấy (với
Frappe HR, cả dòng Expense Claim của công ty ấy); không xoá gì.

`apply_account_categories` tạo các nhóm tài khoản còn thiếu (dùng lại nhóm cơ sở dữ liệu coi là cùng tên), rồi gán
nhóm cho tài khoản chi tiết **chưa có nhóm** theo tiền tố số hiệu (tiền tố dài nhất thắng). Tài khoản chi tiết người
dùng đã gán nhóm khác thì giữ nguyên và được báo ở `accounts_kept`. Tài khoản tổng hợp bị xoá nhóm: một bộ lọc báo
cáo khớp cả 128 lẫn 1281 sẽ cộng một số dư hai lần. Tài khoản chi tiết không tiền tố nào khớp được liệt kê ở
`unplaced` và để nguyên; với cây này đó là 911 và hai tài khoản kỹ thuật không số hiệu. Các nhóm là cách gom của ERPCM
để làm báo cáo, không phải danh mục của Thông tư; mô tả ghi trên từng nhóm nói vậy. 29 nhóm IFRS ERPNext cài sẵn được
để nguyên.

`set_company_defaults` điền các ô tài khoản mặc định của Company từ `tt99_company_defaults.json`. Một ô được điền khi
đang trống, hoặc không trỏ vào một tài khoản chi tiết của công ty; ô người dùng đã chọn một tài khoản chi tiết khác thì
giữ nguyên và được báo ở `kept`. Company được lưu qua kiểm tra của chính ERPNext (ERPNext chỉ kiểm loại tài khoản của
một số ô). Khi công ty đã có bút toán, xem khung ở trên: chỉ phần Frappe HR được điền.

### Tài khoản mặc định: lựa chọn của dự án, kế toán trưởng xem lại

Mọi ô dưới đây là lựa chọn của dự án để ERPNext (và Frappe HR) chạy được ngay; không ô nào là quy định của Thông tư.

| Ô của Company | Tài khoản | Vì sao | Kế toán trưởng có thể muốn |
|---|---|---|---|
| `default_cash_account` | 111 Tiền mặt | ERPNext cần một tài khoản loại Cash. | Một tài khoản chi tiết (1111). |
| `default_receivable_account` | 131 Phải thu của khách hàng | Phải thu khách hàng. | Tài khoản chi tiết theo nhóm khách. |
| `default_payable_account` | 331 Phải trả cho người bán | Phải trả nhà cung cấp. | Tài khoản chi tiết theo nhóm nhà cung cấp. |
| `default_income_account` | 511 Doanh thu bán hàng và cung cấp dịch vụ | Doanh thu mặc định của hoá đơn bán. | Doanh thu theo nhóm hàng (5111, 5112, 5113) trên Item. |
| `default_expense_account` | 632 Giá vốn hàng bán | Giá vốn mặc định. | — |
| `default_inventory_account` | 156 Hàng hóa | Tồn kho khi kho chưa có tài khoản riêng. | 152 / 153 / 155 trên từng kho (Warehouse.account). |
| `stock_received_but_not_billed` | 3389 | Tài khoản kỹ thuật của ERPNext (bổ sung). | — |
| `asset_received_but_not_billed` | 3385 | Tài khoản kỹ thuật của ERPNext (bổ sung). | — |
| `round_off_account` | 6428 Chi phí bằng tiền khác | ERPNext cần một tài khoản loại Round Off cho chênh lệch làm tròn; 6428 cũng là tài khoản của Expense Claim. | 711 / 811 theo dấu của chênh lệch. |
| `exchange_gain_loss_account` | 635 Chi phí tài chính | ERPNext ghi cả lãi lẫn lỗ tỷ giá vào một tài khoản. | Thông lệ Việt Nam tách lãi vào 515, lỗ vào 635. |
| `depreciation_expense_account` | 6424 Chi phí khấu hao TSCĐ (quản lý) | Khấu hao mặc định. | 6274 / 6414 theo bộ phận, đặt trên Asset Category. |
| `accumulated_depreciation_account` | 2141 Hao mòn TSCĐ hữu hình | Hao mòn mặc định. | 2142 / 2143 trên Asset Category. |
| `disposal_account` | 811 Chi phí khác | ERPNext ghi cả lãi lẫn lỗ thanh lý vào một tài khoản, nên lãi thanh lý ghi có vào một tài khoản chi phí. | Lãi vào 711, lỗ vào 811. |
| `capital_work_in_progress_account` | 2411 Mua sắm TSCĐ | Tài sản đang mua. | 2412 khi tự xây dựng. |
| `stock_adjustment_account` | 811 Chi phí khác (loại Stock Adjustment) | ERPNext đòi loại Stock Adjustment cho nhập, xuất kho không qua mua bán. | 632, hoặc 1381 / 3381 cho thiếu, thừa chờ xử lý. |
| `write_off_account` | 811 Chi phí khác | Khoản chênh nhỏ được xoá. | 711 / 811 theo dấu, hoặc 6428. |
| `default_payroll_payable_account` (Frappe HR) | 334 Phải trả người lao động (loại Payable) | Frappe HR đòi loại Payable. | 3341 / 3348 theo loại người lao động. |
| `default_employee_advance_account` (Frappe HR) | 141 Tạm ứng (loại Receivable) | Frappe HR đòi loại Receivable. | Tài khoản chi tiết của 141. |
| tài khoản của Expense Claim Type (Frappe HR) | 6428 Chi phí bằng tiền khác | Để Frappe HR không tự tạo "Expense Claims". | 6421 / 6411 theo bộ phận, trên từng Expense Claim Type. |

Ô `unrealized_exchange_gain_loss_account` để trống, như ở công ty do setup wizard tạo; Exchange Rate Revaluation cần ô
này (ví dụ 413). Tài khoản 1385 (Số dư đầu kỳ tạm) theo tiền tố 138 nằm trong nhóm "Phải thu khác": số dư của nó phải
về 0 sau khi nhập số dư đầu kỳ, nếu không nó hiện lên báo cáo như một khoản phải thu khác.

Trên ERPNext 16.55, ô `write_off_amount` của Sales Invoice chỉ ghi sổ với hoá đơn POS; ngoài POS, khoản chênh nhỏ được
xoá qua dòng khấu trừ (deductions) của Payment Entry trên `write_off_account`.

### Giao dịch

Không thao tác nào tự commit: `bench execute` commit khi hàm trả về không lỗi, một request POST thành công thì Frappe
commit lúc request kết thúc; khi hàm báo lỗi thì không gì được ghi. Mỗi thao tác ghi từ chối chạy trong một giao dịch
đã có lệnh ghi chưa commit, hay khi Frappe đang tắt điều khiển giao dịch (trong một doc_events hay Server Script), để lỗi
giữa chừng chỉ huỷ phần việc của chính nó; `create_company` và `setup_chart` còn kiểm giới hạn lệnh ghi (trên). Trên
MariaDB trước 11.6.2 (`innodb_snapshot_isolation` tắt), việc ERPNext dựng lại nested set của mọi tài khoản có thể đụng
với một tài khoản đang được thêm ở công ty khác cùng lúc — đúng như khi ERPNext tự tạo một công ty.


## Kết chuyển cuối kỳ và 911

Dùng 911 làm tài khoản kết chuyển của Period Closing Voucher thì lãi lỗ của kỳ được chuyển vào 911 và **nằm lại trên
911** cho đến khi có bút toán chuyển sang 4212. 911 không thuộc nhóm tài khoản nào, nên trong lúc đó số dư ấy không lên
dòng báo cáo nào dựng theo nhóm. Cách khác là dùng thẳng 4212 làm tài khoản kết chuyển.

## Giới hạn

- Chưa đối chiếu với văn bản Thông tư (xem dưới).
- Không thay hệ thống tài khoản của một công ty đã có; chỉ tạo công ty mới.
- Mọi thao tác ghi đều từ chối khi công ty đã có bút toán.
- Chưa có báo cáo tài chính theo mẫu B01-DN, B02-DN, B03-DN; các nhóm tài khoản mới là bước chuẩn bị cho chúng.
- Chưa có mẫu thuế GTGT theo cây mới.
- Đã thử trên ERPNext 16.55 / Frappe 16.56 (MariaDB 11.8); `pyproject.toml` đòi ít nhất hai bản ấy.

## Đối chiếu với văn bản Thông tư

Việc này cần một người chép danh mục tài khoản từ văn bản chính thức của Phụ lục II vào
`erpcm/vn/accounting/data/tt99_appendix_ii.json`, dạng:

```json
{"source": "nơi lấy văn bản, ngày", "accounts": [{"number": "111", "name": "Tiền mặt"}]}
```

Khi tệp có mặt, test `test_chart_minus_additions_equals_the_transcribed_appendix` so tập số hiệu của cây (trừ các mục
`additions`) với tập số hiệu đã chép và chỉ ra từng số lệch. Chưa có tệp thì test đó bị bỏ qua và nói lý do. Dự án
không tự tạo tệp này.
