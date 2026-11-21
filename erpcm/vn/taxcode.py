"""Vietnamese tax code (mã số thuế) validation.

Offline and deterministic. A 10-digit MST carries a check digit, so a typo is
catchable without asking anyone — which matters because the expensive failure is
issuing an e-invoice to a mistyped MST: correcting it costs an adjustment or
replacement invoice plus an explanation, while checking it costs nothing.

    N1..N9  N10 = check digit
    weights 31, 29, 23, 19, 17, 13, 7, 5, 3
    N10 = 10 - (sum(Ni * Wi) mod 11)

A 13-digit MST is a 10-digit parent plus a 3-digit branch suffix, written
0123456789-001. Only the parent carries the check digit.

The formula was derived and then checked against three real tax codes whose
values are public — see tests. That is verification, not recall: an earlier
reading of the rule said `11 - (sum mod 11)`, which fails all three.
"""

import re

WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)

PATTERN = re.compile(r"^(\d{10})(?:-(\d{3}))?$")


class InvalidTaxCode(ValueError):
	pass


def normalise(raw):
	"""Strip the punctuation people type, keep the shape that means something."""
	if raw is None:
		return ""
	compact = re.sub(r"[\s.]", "", str(raw)).strip()
	# 13 digits written without the hyphen is common and unambiguous.
	if re.fullmatch(r"\d{13}", compact):
		compact = f"{compact[:10]}-{compact[10:]}"
	return compact


def check_digit(nine):
	total = sum(int(d) * w for d, w in zip(nine, WEIGHTS, strict=True))
	return 10 - (total % 11)


def validate(raw):
	"""Return the normalised MST, or raise InvalidTaxCode saying what is wrong."""
	mst = normalise(raw)
	if not mst:
		raise InvalidTaxCode("mã số thuế trống")

	m = PATTERN.match(mst)
	if not m:
		raise InvalidTaxCode(
			f"{mst!r} không đúng dạng mã số thuế: phải là 10 chữ số, hoặc 10 chữ số kèm 3 chữ số đơn vị trực thuộc"
		)

	parent, branch = m.group(1), m.group(2)
	expected = check_digit(parent[:9])

	# 10 is not a digit, so the first nine digits cannot belong to any issued MST.
	if expected == 10:
		raise InvalidTaxCode(f"{mst!r} không phải mã số thuế hợp lệ: chín chữ số đầu không sinh ra số kiểm tra")

	if int(parent[9]) != expected:
		raise InvalidTaxCode(
			f"{mst!r} sai số kiểm tra: chữ số thứ 10 phải là {expected}, không phải {parent[9]}. "
			"Gần như chắc chắn là lỗi đánh máy."
		)

	if branch is not None and branch == "000":
		raise InvalidTaxCode(f"{mst!r} có mã đơn vị trực thuộc 000, không được cấp")

	return mst


def is_valid(raw):
	try:
		validate(raw)
		return True
	except InvalidTaxCode:
		return False
