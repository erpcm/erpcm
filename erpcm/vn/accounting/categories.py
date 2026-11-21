"""Account Category for the TT99 chart: which reporting category each account belongs to. Pure: no frappe.

A category names the nature of an account (cash, receivables, inventory…); a financial-statement line is
then a sum of categories. Assignment is by account number: the longest matching prefix wins, so 2147
(accumulated depreciation of investment property) is placed before 214 catches it. Only ledger accounts
are assigned — a report filter that matched both 128 and 1281 would count the same balance twice.
"""

import json
import os

from erpcm.vn.accounting.chart import DATA, find, is_group, iter_nodes

CATEGORIES_FILE = os.path.join(DATA, "tt99_categories.json")


def load_categories(path=CATEGORIES_FILE):
	"""The whole categories file: {"categories": [...], "uncategorised": [...], ...}."""
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def prefix_table(categories):
	"""[(prefix, category_name)] longest prefix first, so 2147 is tried before 214."""
	rows = [(str(p), c["name"]) for c in categories for p in c["prefixes"]]
	rows.sort(key=lambda r: (-len(r[0]), r[0]))
	return rows


def category_for(number, table):
	"""The category of an account number, or None when no prefix matches."""
	number = str(number or "")
	if not number:
		return None
	return next((name for prefix, name in table if number.startswith(prefix)), None)


def plan_assignment(accounts, table, company):
	"""(changes, unplaced, kept) for one company's accounts, computed before anything is written.

	accounts: dicts with name, company, account_number, is_group, account_category. A row of any other
	          company is ignored: it is neither changed nor reported.
	changes:  [(account_name, current_category, wanted_category)]: a ledger without a category gets the
	          one its prefix gives; a group has its category cleared (a report filter must not count one
	          balance twice).
	unplaced: names of ledger accounts no prefix reaches; left untouched.
	kept:     [(account_name, current_category, chart_category)]: a ledger a person already gave another
	          category keeps it, and is reported.
	"""
	changes, unplaced, kept = [], [], []
	for a in accounts:
		if a.get("company") != company:
			continue
		current = a.get("account_category") or None
		if a.get("is_group"):
			if current is not None:
				changes.append((a["name"], current, None))
			continue
		want = category_for(a.get("account_number"), table)
		if want is None:
			unplaced.append(a["name"])
		elif current is None:
			changes.append((a["name"], current, want))
		elif current != want:
			kept.append((a["name"], current, want))
	return changes, unplaced, kept


def category_conflicts(categories, existing):
	"""(missing, conflicts): categories to create, and sentences for those that exist with another root_type.

	existing: {category name: root_type} of the Account Categories already on the site.
	"""
	missing, conflicts = [], []
	for c in categories:
		if c["name"] not in existing:
			missing.append(c)
		elif existing[c["name"]] != c["root_type"]:
			conflicts.append(f"Account Category {c['name']} đã có với root_type {existing[c['name']]}")
	return missing, conflicts


def _uncategorised(data, tree):
	"""Node names the categories file declares as deliberately without a category."""
	out = set()
	for entry in data.get("uncategorised") or []:
		if entry.get("number"):
			hit = find(tree, entry["number"])
			if hit:
				out.add(hit[0])
		elif entry.get("name"):
			out.add(entry["name"])
	return out


def validate_categories(data, tree):
	"""Problems with the categories file against the chart, as sentences. Empty means usable.

	data is the whole file (load_categories()), so the declared exceptions are checked too.
	"""
	problems = []
	categories = data["categories"]
	table = prefix_table(categories)

	names = [c["name"] for c in categories]
	for name in sorted({n for n in names if names.count(n) > 1}):
		problems.append(f"nhóm {name!r} khai hai lần")

	prefixes = [p for p, _ in table]
	for p in sorted({p for p in prefixes if prefixes.count(p) > 1}):
		problems.append(f"tiền tố {p} thuộc hai nhóm")

	root_of = {c["name"]: c.get("root_type") for c in categories}
	skip = _uncategorised(data, tree)
	reached = set()
	for _, name, node, root_type in iter_nodes(tree):
		if is_group(node):
			continue
		number = str(node.get("account_number") or "")
		category = category_for(number, table)
		if name in skip:
			if category:
				problems.append(
					f"{number or name!r} khai là không có nhóm nhưng tiền tố đưa nó vào {category!r}"
				)
			continue
		if category is None:
			problems.append(f"tài khoản chi tiết {number or name!r} không thuộc nhóm nào")
			continue
		reached.update(p for p, c in table if c == category and number.startswith(p))
		if root_of[category] != root_type:
			problems.append(
				f"{number} thuộc gốc {root_type}, nhưng nhóm {category!r} khai root_type {root_of[category]}"
			)

	for p in sorted(set(prefixes) - reached):
		problems.append(f"tiền tố {p} không khớp tài khoản chi tiết nào")
	return problems
