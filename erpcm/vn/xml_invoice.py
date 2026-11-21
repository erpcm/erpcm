"""Read a Vietnamese e-invoice XML (ND 123/2020, QD 1450/QD-TCT) into a dict.

Why this exists: the tax authority's portal holds every invoice the company
issued or received, and exports them as XML. Reading that file is how purchase
invoices stop being retyped from PDFs — and how the bang ke mua vao gets checked
against what the tax office actually holds.

Why it is written this way. The element names below come from the published
structure of QD 1450 and are **not verified against a real file** — that needs
one invoice XML from the portal, which is a 30-second download and the last
thing missing. So:

- The names are DATA (FIELD_MAP), not code. Correcting one is editing a dict.
- Each field accepts several candidate names, matched on local-name so a
  namespace prefix cannot break it.
- A missing required field raises with the list of names actually present, so
  the fix is obvious rather than a guess.
- inspect() dumps the tree of a real file. Run it on the first download and the
  map is finished.

Parsing is deliberately read-only and side-effect free: what to *do* with a
parsed invoice — match a supplier, match items, create a Purchase Invoice — needs
business rules that do not exist yet, and guessing them would be worse than
leaving the step to a person.
"""

import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

# Candidate local-names per logical field, best first. Add to a list rather than
# editing code when a real file disagrees.
FIELD_MAP = {
	"invoice": {
		"template_code": ["KHMSHDon"],
		"series": ["KHHDon"],
		"number": ["SHDon"],
		"date": ["NLap"],
		"currency": ["DVTTe"],
		"exchange_rate": ["TGia"],
		"tax_authority_code": ["MCCQT"],
	},
	"seller": {
		"container": ["NBan"],
		"name": ["Ten"],
		"tax_code": ["MST"],
		"address": ["DChi"],
	},
	"buyer": {
		"container": ["NMua"],
		"name": ["Ten"],
		"tax_code": ["MST"],
		"address": ["DChi"],
	},
	"line": {
		"container": ["HHDVu"],
		"index": ["STT"],
		"name": ["THHDVu"],
		"uom": ["DVTinh"],
		"qty": ["SLuong"],
		"rate": ["DGia"],
		"amount": ["ThTien"],
		"tax_percent": ["TSuat"],
	},
	"totals": {
		"container": ["TToan"],
		"amount_without_tax": ["TgTCThue"],
		"tax_amount": ["TgTThue"],
		"amount_with_tax": ["TgTTTBSo"],
	},
}


class XmlInvoiceError(ValueError):
	"""The file is not an invoice we can read, and why."""


def _local(tag):
	"""Strip any namespace: '{urn:x}SHDon' -> 'SHDon'."""
	return tag.rsplit("}", 1)[-1]


def _first(node, names):
	"""First descendant whose local-name is in `names`, in the order given."""
	for name in names:
		for el in node.iter():
			if _local(el.tag) == name:
				return el
	return None


def _text(node, names):
	el = _first(node, names)
	return (el.text or "").strip() if el is not None and el.text else None


# QD 1450 stores numbers plain — 1000000, or 1000000.5 — so separators should
# not appear at all. They are handled anyway because portal exports and provider
# files are not always the standard, but only where the meaning is unambiguous.
#
# The trap: "100.000" is 100000 in Vietnamese notation and 100 as a decimal, and
# picking wrong is an error of 1000x on a tax document. Same for "1,000" read as
# anglo thousands or Vietnamese decimal.
#
# What settles it is the number of groups, not the separator. TWO or more groups
# can only be thousands ("1.000.000" is not a number with two decimal points).
# Exactly ONE group of three digits is ambiguous either way, and is REFUSED.
_THOUSANDS = re.compile(r"^-?\d{1,3}([.,]\d{3}){2,}$")
_AMBIGUOUS = re.compile(r"^-?\d+[.,]\d{3}$")


def _decimal(node, names):
	raw = _text(node, names)
	if raw is None:
		return None

	cleaned = raw.replace(" ", "").replace("\u00a0", "")

	if "," in cleaned and "." in cleaned:
		# Both present: whichever comes last is the decimal separator. Unambiguous.
		if cleaned.rfind(",") > cleaned.rfind("."):
			cleaned = cleaned.replace(".", "").replace(",", ".")
		else:
			cleaned = cleaned.replace(",", "")
	elif _THOUSANDS.match(cleaned):
		cleaned = cleaned.replace(".", "").replace(",", "")
	elif _AMBIGUOUS.match(cleaned):
		grouped = re.sub(r"[.,]", "", cleaned)
		decimal_reading = cleaned.replace(",", ".")
		raise XmlInvoiceError(
			f"{names[0]}: {raw!r} nhập nhằng — có thể là {grouped} (dấu phân nhóm nghìn) "
			f"hoặc {decimal_reading} (dấu thập phân). Lệch 1000 lần nên không đoán. "
			"Sửa nguồn xuất file, hoặc bổ sung quy tắc vào _decimal()."
		)
	elif "," in cleaned:
		cleaned = cleaned.replace(",", ".")

	try:
		return Decimal(cleaned)
	except InvalidOperation as e:
		raise XmlInvoiceError(f"{names[0]}: {raw!r} is not a number") from e


def _names_present(root, limit=60):
	seen = []
	for el in root.iter():
		name = _local(el.tag)
		if name not in seen:
			seen.append(name)
		if len(seen) >= limit:
			break
	return seen


def inspect(xml_text):
	"""Every distinct element name in the file, with one sample value each.

	Run this on the first real download from the portal; the output is what
	finishes FIELD_MAP.
	"""
	root = ET.fromstring(xml_text)
	out = {}
	for el in root.iter():
		name = _local(el.tag)
		if name in out:
			continue
		value = (el.text or "").strip() if el.text else ""
		out[name] = value[:60]
	return out


def parse(xml_text):
	"""Parse one invoice XML. Raises XmlInvoiceError with a usable message."""
	try:
		root = ET.fromstring(xml_text)
	except ET.ParseError as e:
		raise XmlInvoiceError(f"không phải XML hợp lệ: {e}") from e

	inv = FIELD_MAP["invoice"]
	number = _text(root, inv["number"])
	if not number:
		raise XmlInvoiceError(
			"không tìm thấy số hóa đơn. Các element có trong file: "
			+ ", ".join(_names_present(root))
			+ ". Sửa FIELD_MAP trong erpcm/vn/xml_invoice.py."
		)

	def party(key):
		spec = FIELD_MAP[key]
		node = _first(root, spec["container"])
		if node is None:
			return {}
		return {
			"name": _text(node, spec["name"]),
			"tax_code": _text(node, spec["tax_code"]),
			"address": _text(node, spec["address"]),
		}

	line_spec = FIELD_MAP["line"]
	lines = []
	for node in root.iter():
		if _local(node.tag) not in line_spec["container"]:
			continue
		lines.append(
			{
				"index": _text(node, line_spec["index"]),
				"name": _text(node, line_spec["name"]),
				"uom": _text(node, line_spec["uom"]),
				"qty": _decimal(node, line_spec["qty"]),
				"rate": _decimal(node, line_spec["rate"]),
				"amount": _decimal(node, line_spec["amount"]),
				"tax_percent": _text(node, line_spec["tax_percent"]),
			}
		)

	tot_spec = FIELD_MAP["totals"]
	tot_node = _first(root, tot_spec["container"])
	if tot_node is None:
		tot_node = root
	totals = {
		"amount_without_tax": _decimal(tot_node, tot_spec["amount_without_tax"]),
		"tax_amount": _decimal(tot_node, tot_spec["tax_amount"]),
		"amount_with_tax": _decimal(tot_node, tot_spec["amount_with_tax"]),
	}

	return {
		"template_code": _text(root, inv["template_code"]),
		"series": _text(root, inv["series"]),
		"number": number,
		"date": _text(root, inv["date"]),
		"currency": _text(root, inv["currency"]) or "VND",
		"exchange_rate": _decimal(root, inv["exchange_rate"]),
		"tax_authority_code": _text(root, inv["tax_authority_code"]),
		"seller": party("seller"),
		"buyer": party("buyer"),
		"lines": lines,
		"totals": totals,
	}


def check_totals(parsed, tolerance=Decimal("1")):
	"""Do the line amounts add up to the stated totals?

	Returns a list of complaints, empty when consistent. Worth doing on every
	import: a file whose lines do not sum to its own total is either being
	misparsed or is not the document it claims to be, and either way the number
	must not silently enter the books.

	Tolerance is one dong — VND totals are rounded per line by the issuer.
	"""
	problems = []
	stated_net = parsed["totals"]["amount_without_tax"]
	line_sum = sum((line["amount"] or Decimal(0) for line in parsed["lines"]), Decimal(0))

	if not parsed["lines"]:
		problems.append("không đọc được dòng hàng hóa nào")
	elif stated_net is not None and abs(line_sum - stated_net) > tolerance:
		problems.append(f"tổng dòng {line_sum} khác tổng tiền chưa thuế {stated_net}")

	net, tax, gross = (parsed["totals"][k] for k in ("amount_without_tax", "tax_amount", "amount_with_tax"))
	if None not in (net, tax, gross) and abs(net + tax - gross) > tolerance:
		problems.append(f"{net} + {tax} khác tổng thanh toán {gross}")

	if not parsed["seller"].get("tax_code"):
		problems.append("không có MST người bán")

	return problems


def looks_like_invoice_xml(text):
	"""Cheap pre-check so a wrong file gets a clear answer, not a stack trace."""
	return bool(re.search(r"<\s*(\w+:)?HDon\b", text or ""))
