"""Where the offline Vietnamese helpers meet Frappe documents.

Kept apart from taxcode.py and vietqr.py so those two stay pure and testable
without a site.
"""

import frappe
from frappe import _

from erpcm.vn.taxcode import InvalidTaxCode, normalise, validate
from erpcm.vn.vietqr import build


def validate_party_tax_id(doc, method=None):
	"""Refuse a mistyped MST on Customer or Supplier, and normalise what is kept.

	Only a present tax_id is checked. Whether one is *required* is a different
	question, answered per document: a consumer sale legitimately has none, while
	ND 70/2025 requires one on a B2B invoice — that check lives in einvoice.api,
	where the invoice's own facts are known.
	"""
	if not doc.get("tax_id"):
		return

	try:
		doc.tax_id = validate(doc.tax_id)
	except InvalidTaxCode as e:
		frappe.throw(str(e), title=_("Mã số thuế không hợp lệ"))


def assert_valid_tax_id(raw, label):
	"""For callers that hold a raw value rather than a document."""
	try:
		return validate(raw)
	except InvalidTaxCode as e:
		frappe.throw(_("{0}: {1}").format(label, e), title=_("Mã số thuế không hợp lệ"))


def _company_bank(company):
	"""The company's default bank account, and the NAPAS BIN of its bank."""
	# Company.default_bank_account is a LEDGER account (Link → Account, e.g. "1121 - Tiền Việt Nam"),
	# not the name of a Bank Account — look up the Bank Account attached to that ledger account.
	account = None
	gl_account = frappe.db.get_value("Company", company, "default_bank_account")
	if gl_account:
		linked = frappe.get_all(
			"Bank Account",
			filters={"company": company, "is_company_account": 1, "account": gl_account},
			pluck="name",
		)
		account = linked[0] if linked else None
	if not account:
		accounts = frappe.get_all(
			"Bank Account",
			filters={"company": company, "is_company_account": 1, "is_default": 1},
			pluck="name",
		)
		account = accounts[0] if accounts else None
	if not account:
		return None, None

	row = frappe.db.get_value("Bank Account", account, ["bank", "bank_account_no"], as_dict=True)
	if not row or not row.bank_account_no:
		return None, None

	return frappe.db.get_value("Bank", row.bank, "custom_napas_bin"), row.bank_account_no


def vietqr_for_sales_invoice(name):
	"""The VietQR payload for an invoice, or None.

	**Never raises.** This is called from a print format, and a print format that
	throws makes the invoice unprintable — which is a worse outcome than a missing
	QR code. Every reason for None is logged instead.
	"""
	try:
		si = frappe.db.get_value(
			"Sales Invoice",
			name,
			["company", "currency", "outstanding_amount", "grand_total", "name"],
			as_dict=True,
		)
		if not si:
			return None

		# A QR that names a dong amount on a foreign-currency invoice would be
		# worse than no QR.
		if si.currency != "VND":
			return None

		bank_bin, account_no = _company_bank(si.company)
		if not bank_bin or not account_no:
			frappe.logger("vietqr").info(
				f"{name}: no default company Bank Account with a NAPAS BIN on its Bank"
			)
			return None

		amount = si.outstanding_amount if (si.outstanding_amount or 0) > 0 else si.grand_total
		return build(bank_bin, account_no, amount=amount, description=si.name)
	except Exception:
		frappe.log_error(title=f"VietQR failed for {name}", message=frappe.get_traceback())
		return None


def vietqr_svg_for_sales_invoice(name):
	"""A data: URI holding the VietQR as an SVG image, or None.

	Same contract as vietqr_for_sales_invoice: **never raises**, because this is
	called from a print format.

	SVG base64 in an <img>, which is the pattern frappe already uses for its own
	two-factor QR — proven under wkhtmltopdf, and no dependency beyond the
	pyqrcode frappe already ships.
	"""
	payload = vietqr_for_sales_invoice(name)
	if not payload:
		return None

	try:
		from base64 import b64encode
		from io import BytesIO

		from pyqrcode import create as qrcreate

		stream = BytesIO()
		try:
			# Error correction M: readable after the print is folded or scanned.
			qrcreate(payload, error="M").svg(stream, scale=5, background="#fff", module_color="#000")
			svg = stream.getvalue().decode().replace("\n", "")
		finally:
			stream.close()

		return "data:image/svg+xml;base64," + b64encode(svg.encode()).decode()
	except Exception:
		frappe.log_error(title=f"VietQR SVG failed for {name}", message=frappe.get_traceback())
		return None


def normalise_tax_id(raw):
	"""Exposed for templates and reports that want the tidy form."""
	return normalise(raw)
