"""Fields ERPCM adds to standard doctypes. Safe to run again: existing fields are updated, not duplicated."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Bank": [
		{
			"fieldname": "custom_napas_bin",
			"label": "NAPAS BIN",
			"fieldtype": "Data",
			"length": 8,
			"insert_after": "swift_number",
			"description": "Mã BIN 6 số của ngân hàng trong hệ thống NAPAS, dùng để tạo mã VietQR",
		}
	],
}


def after_install():
	create_custom_fields(CUSTOM_FIELDS, update=True)
