"""Tests for the e-invoice XML reader.

The sample below is built from the published QD 1450 structure, so these tests
prove the parser handles that shape, the number formats, namespaces and the
consistency checks — they do NOT prove the element names match a real portal
file. That needs one real download; see xml_invoice's module docstring.
"""

from decimal import Decimal

from erpcm.vn.xml_invoice import (
	XmlInvoiceError,
	check_totals,
	inspect,
	looks_like_invoice_xml,
	parse,
)

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
  <DLHDon>
    <TTChung>
      <KHMSHDon>1</KHMSHDon><KHHDon>C26TAA</KHHDon><SHDon>1234</SHDon>
      <NLap>2026-08-20</NLap><DVTTe>VND</DVTTe><TGia>1</TGia>
    </TTChung>
    <NDHDon>
      <NBan><Ten>Cong ty Ban Hang</Ten><MST>0100112437</MST><DChi>Ha Noi</DChi></NBan>
      <NMua><Ten>Cong ty Mua Hang</Ten><MST>0100150619</MST><DChi>Ha Noi</DChi></NMua>
      <DSHHDVu>
        <HHDVu><STT>1</STT><THHDVu>Hoa chat A</THHDVu><DVTinh>Kg</DVTinh>
          <SLuong>10</SLuong><DGia>100000</DGia><ThTien>1000000</ThTien><TSuat>10%</TSuat></HHDVu>
        <HHDVu><STT>2</STT><THHDVu>Van chuyen</THHDVu><DVTinh>Lan</DVTinh>
          <SLuong>1</SLuong><DGia>500000</DGia><ThTien>500000</ThTien><TSuat>8%</TSuat></HHDVu>
      </DSHHDVu>
      <TToan><TgTCThue>1500000</TgTCThue><TgTThue>140000</TgTThue>
        <TgTTTBSo>1640000</TgTTTBSo></TToan>
    </NDHDon>
  </DLHDon>
  <MCCQT>00123456789ABCDEF</MCCQT>
</HDon>"""



def test_parses_the_documented_shape():
	d = parse(SAMPLE)
	assert d["number"] == "1234"
	assert d["series"] == "C26TAA"
	assert d["date"] == "2026-08-20"
	assert d["seller"]["tax_code"] == "0100112437"
	assert d["buyer"]["tax_code"] == "0100150619"
	assert d["tax_authority_code"] == "00123456789ABCDEF"
	assert len(d["lines"]) == 2, d["lines"]
	assert d["lines"][0]["amount"] == Decimal("1000000"), d["lines"][0]
	assert d["lines"][1]["tax_percent"] == "8%"
	assert d["totals"]["amount_with_tax"] == Decimal("1640000")


def test_separator_styles_that_are_unambiguous():
	"""Files that are not the standard still parse, where the meaning is certain."""
	dotted = SAMPLE.replace("<ThTien>1000000</ThTien>", "<ThTien>1.000.000</ThTien>")
	assert parse(dotted)["lines"][0]["amount"] == Decimal("1000000"), "two dots = thousands"

	euro = SAMPLE.replace("<ThTien>1000000</ThTien>", "<ThTien>1.000.000,50</ThTien>")
	assert parse(euro)["lines"][0]["amount"] == Decimal("1000000.50")

	anglo = SAMPLE.replace("<ThTien>1000000</ThTien>", "<ThTien>1,000,000.50</ThTien>")
	assert parse(anglo)["lines"][0]["amount"] == Decimal("1000000.50")


def test_the_1000x_ambiguity_is_refused():
	"""100.000 is 100000 in VN notation and 100 as a decimal. Guessing is a 1000x error."""
	for risky in ("100.000", "1,000"):
		doc = SAMPLE.replace("<ThTien>1000000</ThTien>", f"<ThTien>{risky}</ThTien>")
		try:
			parse(doc)
		except XmlInvoiceError as e:
			assert "nhập nhằng" in str(e) and "1000" in str(e), e
			continue
		raise AssertionError(f"{risky!r} is ambiguous and must refuse, not guess")

	# One group is ambiguous; two cannot be anything but thousands.
	fine = SAMPLE.replace("<ThTien>1000000</ThTien>", "<ThTien>1.100.000</ThTien>")
	assert parse(fine)["lines"][0]["amount"] == Decimal("1100000")


def test_namespaced_file_still_parses():
	ns = SAMPLE.replace("<HDon>", '<inv:HDon xmlns:inv="urn:x">').replace("</HDon>", "</inv:HDon>")
	ns = ns.replace("<DLHDon>", "<inv:DLHDon>").replace("</DLHDon>", "</inv:DLHDon>")
	d = parse(ns)
	assert d["number"] == "1234", "a namespace prefix must not hide the fields"


def test_totals_check_passes_on_a_consistent_file():
	assert check_totals(parse(SAMPLE)) == []


def test_totals_check_catches_an_inconsistent_file():
	bad = SAMPLE.replace("<TgTTTBSo>1640000</TgTTTBSo>", "<TgTTTBSo>9999999</TgTTTBSo>")
	problems = check_totals(parse(bad))
	assert problems and "tổng thanh toán" in problems[0], problems


def test_missing_number_says_what_it_found():
	broken = SAMPLE.replace("<SHDon>1234</SHDon>", "")
	try:
		parse(broken)
	except XmlInvoiceError as e:
		assert "KHHDon" in str(e), "the error must list the names actually present"
		assert "FIELD_MAP" in str(e), "and point at where to fix it"
		return
	raise AssertionError("a file with no invoice number must refuse")


def test_rejects_non_xml_and_wrong_files():
	try:
		parse("this is not xml")
	except XmlInvoiceError as e:
		assert "XML" in str(e)
	assert looks_like_invoice_xml(SAMPLE)
	assert not looks_like_invoice_xml("<Something/>")


def test_inspect_lists_the_tree():
	names = inspect(SAMPLE)
	for expected in ("SHDon", "NBan", "MST", "TgTTTBSo", "HHDVu"):
		assert expected in names, f"{expected} missing from inspect()"
	assert names["SHDon"] == "1234"
