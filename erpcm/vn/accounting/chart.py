"""The Vietnamese chart of accounts as data, and the decisions taken on it. Pure: no frappe import.

The chart is a tree in the shape ERPNext's create_charts() reads (custom_chart=): a node is a dict whose
keys are either metadata (CHART_META) or the names of its children. root_type is declared once on each
root and inherited downwards, which is how create_charts reads it.

The data is modelled on Appendix II of Circular 99/2025/TT-BTC and has NOT been checked number by number
against the circular's text. The file's `additions` lists the nodes the project knows are not in the
circular; that list has not been checked against the text either.
"""

import copy
import json
import os

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CHART_FILE = os.path.join(DATA, "tt99_chart.json")

# ERPNext's get_chart_metadata_fields() on v16.55: the keys of a node that are not children.
CHART_META = frozenset(
	{
		"account_name",
		"account_number",
		"account_type",
		"account_category",
		"root_type",
		"is_group",
		"tax_rate",
		"account_currency",
	}
)

ROOT_TYPES = frozenset({"Asset", "Liability", "Equity", "Income", "Expense"})

# Account.account_type options on ERPNext v16.55, verbatim.
ACCOUNT_TYPES = frozenset(
	{
		"Accumulated Depreciation",
		"Asset Received But Not Billed",
		"Bank",
		"Cash",
		"Chargeable",
		"Capital Work in Progress",
		"Cost of Goods Sold",
		"Current Asset",
		"Current Liability",
		"Depreciation",
		"Direct Expense",
		"Direct Income",
		"Equity",
		"Expense Account",
		"Expenses Included In Asset Valuation",
		"Expenses Included In Valuation",
		"Fixed Asset",
		"Income Account",
		"Indirect Expense",
		"Indirect Income",
		"Liability",
		"Payable",
		"Receivable",
		"Round Off",
		"Round Off for Opening",
		"Stock",
		"Stock Adjustment",
		"Stock Received But Not Billed",
		"Service Received But Not Billed",
		"Tax",
		"Temporary",
	}
)

NAME_SEPARATOR = " / "
NAME_STYLES = ("vi", "vi_en")

# The account Period Closing Voucher closes the year into. It must sit under an Equity (or Liability) root.
CLOSING_ACCOUNT = "911"

VERDICTS = ("BUILD", "MATCH", "DIFFERENT")


def load_chart(path=CHART_FILE):
	"""The whole chart file: {"name", "country_code", "additions", "tree", ...}."""
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def _children(node):
	return [k for k, v in node.items() if k not in CHART_META and isinstance(v, dict)]


def iter_nodes(tree):
	"""Yield (parent_name, name, node, root_type) depth-first, in file order. Roots have parent_name None."""

	def walk(node, parent, root_type):
		for name in _children(node):
			child = node[name]
			inherited = child.get("root_type") if parent is None else root_type
			yield parent, name, child, inherited
			yield from walk(child, name, inherited)

	yield from walk(tree, None, None)


def is_group(node):
	return 1 if (node.get("is_group") or _children(node)) else 0


def flatten(tree):
	"""{(parent_name, name): (number, account_type, root_type, is_group)} — the fields the chart owns.

	Keyed on the pair rather than the name alone because the chart reuses names under different parents
	(6232 and 6272 are both "Chi phí vật liệu"). account_category is absent on purpose: categories are set
	by their own action, and comparing them here would make a category change look like chart drift.
	"""
	out = {}
	for parent, name, node, root_type in iter_nodes(tree):
		out[(parent, name)] = (
			str(node.get("account_number") or "") or None,
			node.get("account_type") or None,
			root_type,
			is_group(node),
		)
	return out


def numbers(tree):
	"""Every account number in the tree, as strings."""
	return {str(n["account_number"]) for _, _, n, _ in iter_nodes(tree) if n.get("account_number")}


def find(tree, number):
	"""(name, node, parent_node) of the account numbered `number`, or None."""
	number = str(number)

	def walk(node):
		for name in _children(node):
			child = node[name]
			if str(child.get("account_number") or "") == number:
				return name, child, node
			hit = walk(child)
			if hit:
				return hit
		return None

	return walk(tree)


def vi_name(name):
	"""'Tiền mặt / Cash on Hand' -> 'Tiền mặt'. A name without the separator is returned unchanged."""
	return name.split(NAME_SEPARATOR, 1)[0].strip()


def with_names(tree, names):
	"""A copy of the tree with account names in the chosen style: "vi_en" as stored, "vi" Vietnamese only.

	Raises ValueError rather than silently merging two siblings that become the same name.
	"""
	if names not in NAME_STYLES:
		raise ValueError(f"names phải là một trong {NAME_STYLES}, không phải {names!r}")
	if names == "vi_en":
		return copy.deepcopy(tree)

	def rename(node, path):
		out = {}
		for key, value in node.items():
			if key in CHART_META or not isinstance(value, dict):
				out[key] = copy.deepcopy(value)
				continue
			new = vi_name(key)
			if new in out:
				raise ValueError(f"hai tài khoản cùng tên {new!r} dưới {path or '(gốc)'}")
			out[new] = rename(value, new)
		return out

	return rename(tree, None)


def validate_chart(tree):
	"""Problems with the tree, as sentences. An empty list means the tree is usable."""
	problems = []
	seen_numbers = {}
	seen_keys = set()

	def walk(node, parent, root_type, numbered_ancestor, path):
		for name in _children(node):
			child = node[name]
			here = path + (name,)
			if parent is None:
				root_type = child.get("root_type")
				if root_type not in ROOT_TYPES:
					problems.append(f"gốc {name!r} không có root_type hợp lệ ({root_type!r})")
			elif "root_type" in child:
				problems.append(f"{name!r}: root_type chỉ được khai ở gốc, create_charts bỏ qua nó ở đây")

			key = (parent, name)
			if key in seen_keys:
				problems.append(f"hai tài khoản {name!r} dưới cùng một tên cha {parent!r}")
			seen_keys.add(key)

			number = str(child.get("account_number") or "")
			if number:
				if not number.isdigit():
					problems.append(f"{name!r}: số hiệu {number!r} không phải dãy chữ số")
				if number in seen_numbers:
					problems.append(f"số hiệu {number} dùng hai lần: {seen_numbers[number]!r} và {name!r}")
				seen_numbers[number] = name
				if numbered_ancestor and not (
					number.startswith(numbered_ancestor) and number != numbered_ancestor
				):
					problems.append(
						f"{number} {name!r} không nối dài số hiệu của tài khoản cha {numbered_ancestor}"
					)
				if number == CLOSING_ACCOUNT and root_type != "Equity":
					problems.append(
						f"{CLOSING_ACCOUNT} phải nằm dưới một gốc Equity, đang ở gốc {root_type!r}"
					)

			account_type = child.get("account_type")
			if account_type and account_type not in ACCOUNT_TYPES:
				problems.append(f"{name!r}: account_type {account_type!r} không có trong ERPNext")
			if account_type and _children(child):
				problems.append(f"{name!r}: tài khoản tổng hợp không mang account_type")

			for key_name, value in child.items():
				if key_name not in CHART_META and not isinstance(value, dict):
					problems.append(f"{name!r}: khoá lạ {key_name!r}")

			walk(child, name, root_type, number or numbered_ancestor, here)

	walk(tree, None, None, "", ())
	if CLOSING_ACCOUNT not in seen_numbers:
		problems.append(f"thiếu tài khoản {CLOSING_ACCOUNT}")
	return problems


def _sort_key(key):
	parent, name = key
	return (parent or "", name)


def diff(want, have):
	"""[(key, want_row, have_row)] for every key where the two flattened charts differ, in a stable order.

	A missing side is None: (key, row, None) is an account the chart has and the company lacks.
	"""
	return [
		(k, want.get(k), have.get(k))
		for k in sorted(set(want) | set(have), key=_sort_key)
		if want.get(k) != have.get(k)
	]


def decide(account_count, style):
	"""Where a company's chart stands. Pure, so the table is testable without a site.

	BUILD      the company has no account: setup_chart may build the chart.
	MATCH      the company's accounts equal the TT99 chart in one of the two name styles (`style`).
	DIFFERENT  the company has another chart. ERPCM never replaces an existing chart: deleting accounts on
	           a live site cannot be made safe from inside an app (docs/ke-toan-tt99.md); create_company
	           makes a new company with the TT99 chart instead.
	"""
	if not account_count:
		return "BUILD"
	return "MATCH" if style else "DIFFERENT"
