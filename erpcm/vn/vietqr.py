"""VietQR payload builder — EMVCo TLV over the NAPAS profile.

Fully offline: the QR is computed, not fetched, so there is no provider, no key
and nothing to fail at closing time. Only the beneficiary bank's NAPAS BIN and
account number are needed.

Structure, per NAPAS's VietQR format:

    00 02 01                 payload format indicator
    01 02 11|12              11 = static (no amount), 12 = dynamic
    38 ..                    merchant account information
       00 10 A000000727      NAPAS GUID
       01 ..                 beneficiary
          00 06 <bank BIN>
          01 .. <account no>
       02 08 QRIBFTTA        transfer to account
    53 03 704                currency VND
    54 .. <amount>           dynamic only, integer dong
    58 02 VN                 country
    62 ..                    additional data
       08 .. <description>
    63 04 <CRC16>            over everything including "6304"

The CRC implementation is verified against a published real VietQR payload; the
field structure follows the NAPAS format document.

One thing that published payload is *not* good for: it emits "00" as the payload
format indicator where EMVCo requires "01" — its own parser calls that field
"Version". So it is used as the oracle for CRC only, and the structure is
asserted field by field instead. See tests.
"""

GUID = "A000000727"
SERVICE_TRANSFER_TO_ACCOUNT = "QRIBFTTA"
CURRENCY_VND = "704"
COUNTRY_VN = "VN"


def tlv(tag, value):
	"""EMVCo field. Length is two decimal digits, so a value must be < 100 chars."""
	if len(value) > 99:
		raise ValueError(f"tag {tag}: value is {len(value)} chars, EMVCo allows 99")
	return f"{tag}{len(value):02d}{value}"


def crc16(payload):
	"""CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no xorout."""
	crc = 0xFFFF
	for ch in payload.encode("utf-8"):
		crc ^= ch << 8
		for _ in range(8):
			crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
	return f"{crc:04X}"


def build(bank_bin, account_number, amount=None, description=None):
	"""Return the VietQR payload string to render as a QR code.

	amount None makes a static QR — the payer types the amount. Passing an
	amount makes it dynamic, which is what an invoice wants: the payer cannot
	mistype it.
	"""
	if not bank_bin or not str(bank_bin).isdigit():
		raise ValueError(f"bank BIN must be digits, got {bank_bin!r}")
	if not account_number:
		raise ValueError("account number is required")

	beneficiary = tlv("00", str(bank_bin)) + tlv("01", str(account_number))
	merchant = tlv("00", GUID) + tlv("01", beneficiary) + tlv("02", SERVICE_TRANSFER_TO_ACCOUNT)

	body = tlv("00", "01")
	# 11 static, 12 dynamic. Both branches used to say 12 — a real bug caught by
	# writing the test that asserts the two forms differ.
	body += tlv("01", "11" if amount is None else "12")
	body += tlv("38", merchant)
	body += tlv("53", CURRENCY_VND)
	if amount is not None:
		# VND has no subunit, and a decimal point here is rejected by some apps.
		body += tlv("54", str(int(round(float(amount)))))
	body += tlv("58", COUNTRY_VN)
	if description:
		body += tlv("62", tlv("08", description))

	unsigned = body + "6304"
	return unsigned + crc16(unsigned)
