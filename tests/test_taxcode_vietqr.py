"""Tests for the offline Vietnamese helpers, against published real values."""

from erpcm.vn import vietqr
from erpcm.vn.taxcode import InvalidTaxCode, check_digit, normalise, validate

# Real, public tax codes. Three, because two could agree by luck: an earlier
# reading of the rule (11 - sum%11) passes none of them.
REAL = {
	"0100109106": "Viettel",
	"0100112437": "Vietcombank",
	"0100150619": "BIDV",
}

# A published real VietQR payload: Vietcombank (BIN 970436), account
# 0881000458086. Used as the oracle for CRC16 only — it emits "00" as the
# payload format indicator where EMVCo requires "01", so it cannot be the oracle
# for structure. Finding that out is why the structure is asserted field by
# field below rather than against a single string.
PUBLISHED = "00020001021238570010A00000072701270006970436011308810004580860208QRIBFTTA53037045802VN6304CD60"



def test_real_tax_codes_validate():
	for mst, who in REAL.items():
		assert validate(mst) == mst, f"{who} {mst} rejected"
		assert check_digit(mst[:9]) == int(mst[9]), f"{who}: check digit mismatch"


def test_a_typo_is_caught():
	# Swap two digits of a real MST — the classic typo.
	bad = "0100112473"  # Vietcombank's 0100112437 with the last two swapped
	try:
		validate(bad)
	except InvalidTaxCode as e:
		assert "số kiểm tra" in str(e), e
		return
	raise AssertionError("a transposition typo must be caught")


def test_branch_codes():
	assert validate("0100109106-997") == "0100109106-997"
	assert validate("0100109106997") == "0100109106-997", "13 digits without a hyphen"
	for bad in ("0100109106-000", "0100109106-1", "abc", "", None, "01001091"):
		try:
			validate(bad)
		except InvalidTaxCode:
			continue
		raise AssertionError(f"{bad!r} should have been rejected")


def test_normalising():
	assert normalise(" 0100.109.106 ") == "0100109106"
	assert normalise(None) == ""


def test_crc_matches_a_real_payload():
	"""The one thing the published payload proves: our CRC16 is the right CRC16."""
	assert vietqr.crc16(PUBLISHED[:-4]) == PUBLISHED[-4:]


def test_structure_follows_the_spec():
	qr = vietqr.build("970436", "0881000458086")
	# Field by field, because a single golden string cannot say which field is wrong.
	assert qr.startswith("000201"), "payload format indicator must be 01"
	assert qr[6:12] == "010211", "no amount means a static QR, initiation method 11"
	assert "0010A000000727" in qr, "NAPAS GUID"
	assert "0006970436" in qr, "bank BIN"
	assert "01130881000458086" in qr, "account number"
	assert "0208QRIBFTTA" in qr, "transfer-to-account service code"
	assert "5303704" in qr, "currency VND"
	assert "5802VN" in qr, "country"
	assert "54" not in qr[12:qr.index("5303704")], "a static QR carries no amount"
	assert vietqr.crc16(qr[:-4]) == qr[-4:]


def test_static_and_dynamic_differ():
	static = vietqr.build("970436", "0881000458086")
	dynamic = vietqr.build("970436", "0881000458086", amount=1000)
	assert static[6:12] == "010211" and dynamic[6:12] == "010212"


def test_vietqr_dynamic_carries_amount_and_note():
	qr = vietqr.build("970418", "12345678", amount=1_500_000, description="ACC-SINV-2026-00001")
	assert "5407150000" in qr, "amount 1500000 should appear as tag 54 length 07"
	assert "ACC-SINV-2026-00001" in qr
	assert vietqr.crc16(qr[:-4]) == qr[-4:], "CRC must still verify"
	assert "0006970418" in qr, "BIDV BIN"


def test_vietqr_rejects_nonsense():
	for args in (("", "123"), ("97x436", "123"), ("970436", "")):
		try:
			vietqr.build(*args)
		except ValueError:
			continue
		raise AssertionError(f"{args} should have been rejected")
