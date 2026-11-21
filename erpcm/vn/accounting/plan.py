"""What each action would do, decided from plain data before anything is written. Pure: no frappe import.

setup.py collects the facts from the site (the company's accounts, the posting counts, the Company's
default-account fields) and hands them here.
"""

from erpcm.vn.accounting.chart import NAME_STYLES, diff, flatten, iter_nodes, with_names

# Ledgers whose rows mean the company has started keeping books.
POSTING_DOCTYPES = ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry")


def docname(number, name, abbr):
	"""An Account's name as ERPNext builds it (get_autoname_with_number)."""
	return f"{number} - {name} - {abbr}" if number else f"{name} - {abbr}"


def live_flat(rows):
	"""(flat, duplicates) for a company's Account rows, flattened like chart.flatten.

	rows: dicts with name, account_name, account_number, parent_account, account_type, root_type, is_group.
	duplicates: docnames of every account that shares its (parent name, name) key with another one. Such
	a pair would collapse into one key, so it must never count as a match.
	"""
	by_name = {r["name"]: r for r in rows}
	flat, seen = {}, {}
	for r in rows:
		parent = by_name[r["parent_account"]]["account_name"] if r.get("parent_account") in by_name else None
		key = (parent, r["account_name"])
		seen.setdefault(key, []).append(r["name"])
		flat[key] = (
			r.get("account_number") or None,
			r.get("account_type") or None,
			r.get("root_type"),
			1 if r.get("is_group") else 0,
		)
	duplicates = sorted(n for names in seen.values() if len(names) > 1 for n in names)
	return flat, duplicates


def tt99_style(tree, rows):
	"""The name style in which the company's accounts equal the TT99 chart ("vi_en" or "vi"), or None."""
	have, duplicates = live_flat(rows)
	if not have or duplicates:
		return None
	for style in NAME_STYLES:
		if not diff(flatten(with_names(tree, style)), have):
			return style
	return None


def longest_docname(tree, abbr):
	return max((docname(n.get("account_number"), name, abbr) for _, name, n, _ in iter_nodes(tree)), key=len)


def name_length_problem(tree, abbr, max_length):
	"""A sentence when the longest account name for this abbreviation does not fit ERPNext's column."""
	longest = longest_docname(tree, abbr)
	if len(longest) <= max_length:
		return None
	return (
		f"tên tài khoản dài nhất sẽ là {len(longest)} ký tự ({longest!r}), quá {max_length} ký tự ERPNext "
		f"cho phép: dùng names='vi' hoặc viết tắt công ty ({abbr!r}) ngắn hơn"
	)


def abbr_problem(abbr):
	"""A sentence when the abbreviation is not letters and digits only (it ends every account name)."""
	if abbr and abbr.isalnum():
		return None
	return f"viết tắt công ty chỉ gồm chữ và số, không phải {abbr!r}"


def company_name_problem(company_name, abbr, max_length):
	"""A sentence when a name ERPNext derives from the company name does not fit its column.

	The root Cost Center is named after the company: "<company_name> - <abbr>".
	"""
	derived = f"{company_name} - {abbr}"
	if len(derived) <= max_length:
		return None
	return (
		f"tên công ty quá dài: cost center gốc sẽ tên {len(derived)} ký tự, "
		f"quá {max_length} ký tự ERPNext cho phép"
	)


def write_limit_problem(site_accounts, limit):
	"""A sentence when building a chart could reach the site's write limit.

	create_charts rebuilds the nested set of every Account on the site, and Frappe commits in the middle of
	a transaction that passes max_writes_per_transaction while that rebuild runs. Measured on 16.55
	a build takes about the site's accounts + 400 writes; site accounts x 2 + 1000 leaves room for the rest.
	"""
	needed = site_accounts * 2 + 1000
	if needed < limit:
		return None
	return (
		f"dựng hệ thống tài khoản có thể cần {needed} lệnh ghi, chạm giới hạn {limit} lệnh ghi một giao dịch "
		"của site (max_writes_per_transaction); quá giới hạn ấy Frappe tự commit giữa chừng, "
		"nên ERPCM không chạy"
	)


def may_write(style, posted):
	"""Why apply_account_categories / set_company_defaults must not run, as sentences; empty means go."""
	reasons = []
	if not style:
		reasons.append(
			"hệ thống tài khoản của công ty không phải TT99 của ERPCM (chart_status phải là MATCH)"
		)
	posted = {dt: n for dt, n in (posted or {}).items() if n}
	if posted:
		reasons.append(
			"công ty đã có bút toán: " + ", ".join(f"{n} {dt}" for dt, n in sorted(posted.items()))
		)
	return reasons


def plan_defaults(mapping, ledgers, current):
	"""(changes, kept, missing) for the Company's default-account fields.

	mapping: {field: account number}; ledgers: the company's ledger accounts, dicts with name and
	account_number; current: {field: value now}. A field is set when it is empty or points at anything
	that is not one of the company's ledgers; a field a person set to another ledger is kept.
	"""
	by_number = {}
	for a in ledgers:
		by_number.setdefault(str(a.get("account_number") or ""), []).append(a["name"])
	names = {a["name"] for a in ledgers}
	changes, kept, missing = {}, [], []
	for field, number in mapping.items():
		found = by_number.get(str(number), [])
		if len(found) != 1:
			missing.append(f"{field}: {len(found)} tài khoản chi tiết số {number}")
			continue
		want, now = found[0], current.get(field)
		if now == want:
			continue
		if now and now in names:
			kept.append({"field": field, "current": now, "chart": want})
			continue
		changes[field] = want
	return changes, kept, missing
