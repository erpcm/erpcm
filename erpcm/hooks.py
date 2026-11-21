app_name = "erpcm"
app_title = "ERPCM"
app_publisher = "ERPCM"
app_email = "contact@erpcm.com"
app_description = "Open-source Vietnamese localisation for ERPNext"
app_license = "gpl-3.0"

required_apps = ["frappe/erpnext"]

after_install = "erpcm.install.after_install"

# A mistyped tax code is refused when a Customer or Supplier is saved.
doc_events = {
	"Customer": {"validate": "erpcm.vn.hooks.validate_party_tax_id"},
	"Supplier": {"validate": "erpcm.vn.hooks.validate_party_tax_id"},
}

# Callable from a Print Format. The VietQR helpers never raise: a print format
# that throws makes the invoice unprintable, which is worse than a missing QR.
jinja = {
	"methods": [
		"erpcm.vn.hooks.vietqr_for_sales_invoice",
		"erpcm.vn.hooks.vietqr_svg_for_sales_invoice",
		"erpcm.vn.hooks.normalise_tax_id",
	],
}
