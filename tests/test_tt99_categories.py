"""Tests for the TT99 account categories. No site, no database, no network."""

import json

from erpcm.vn.accounting import chart
from erpcm.vn.accounting.categories import (
	category_conflicts,
	category_for,
	load_categories,
	plan_assignment,
	prefix_table,
	validate_categories,
)

DATA = load_categories()
TABLE = prefix_table(DATA["categories"])
TREE = chart.load_chart()["tree"]
NODES = list(chart.iter_nodes(TREE))


def docname(number, name):
	"""Names repeat in the chart (6232 and 6272 are both "Chi phí vật liệu"); ERPNext's docname does not."""
	return f"{number} - {name}" if number else name


def accounts():
	"""The chart as the account rows a company built from it would hold, before any category is set."""
	return [
		{
			"name": docname(node.get("account_number"), name),
			"account_number": node.get("account_number"),
			"is_group": chart.is_group(node),
			"company": "A",
		}
		for _, name, node, _ in NODES
	]


def declared_uncategorised():
	out = set()
	for entry in DATA["uncategorised"]:
		out.add(
			docname(entry["number"], chart.find(TREE, entry["number"])[0])
			if entry.get("number")
			else entry["name"]
		)
	return out


def test_longest_prefix_wins():
	assert category_for("2147", TABLE) == "Bất động sản đầu tư"
	assert category_for("2141", TABLE) == "Tài sản cố định"
	assert category_for("1281", TABLE) == "Đầu tư tài chính"
	assert category_for("911", TABLE) is None
	assert category_for(None, TABLE) is None


def test_groups_get_no_category():
	rows = accounts()
	for r in rows:
		if r["is_group"]:
			r["account_category"] = "Tiền và tương đương tiền"
	changes, _, _ = plan_assignment(rows, TABLE, "A")
	wanted = {name: want for name, _, want in changes}
	groups = [r["name"] for r in rows if r["is_group"]]
	assert groups
	for name in groups:
		assert wanted.get(name, "unchanged") is None, name


def test_every_leaf_but_the_declared_ones_gets_exactly_one_category():
	changes, unplaced, _ = plan_assignment(accounts(), TABLE, "A")
	skip = declared_uncategorised()
	assert set(unplaced) == skip
	assert len(skip) == 3
	placed = [name for name, _, want in changes if want]
	assert len(placed) == len(set(placed))
	leaves = [r["name"] for r in accounts() if not r["is_group"]]
	assert sorted(placed) == sorted(n for n in leaves if n not in skip)


def test_a_category_root_type_equals_the_root_of_every_leaf_it_reaches():
	root_of = {c["name"]: c["root_type"] for c in DATA["categories"]}
	for _, name, node, root_type in NODES:
		category = category_for(node.get("account_number"), TABLE)
		if category and not chart.is_group(node):
			assert root_of[category] == root_type, (name, category)


def test_no_duplicate_prefix():
	prefixes = [p for c in DATA["categories"] for p in c["prefixes"]]
	assert len(prefixes) == len(set(prefixes)), sorted({p for p in prefixes if prefixes.count(p) > 1})


def test_validate_categories_accepts_the_data_and_names_each_fault():
	assert validate_categories(DATA, TREE) == []

	def broken(change):
		data = json.loads(json.dumps(DATA))
		change(data)
		return validate_categories(data, TREE)

	assert broken(lambda d: d["categories"][0]["prefixes"].append("131"))
	assert broken(lambda d: d["categories"][0].update(root_type="Liability"))
	assert broken(lambda d: d["categories"][0]["prefixes"].remove("113"))
	assert broken(lambda d: d["uncategorised"].pop(0))


def test_a_category_set_on_an_account_the_chart_does_not_know_is_left_alone():
	rows = [
		{"name": "Custom", "company": "A", "account_number": "", "is_group": 0, "account_category": "Mine"}
	]
	changes, unplaced, kept = plan_assignment(rows, TABLE, "A")
	assert changes == [] and kept == []
	assert unplaced == ["Custom"]


def test_a_category_a_person_chose_on_a_known_ledger_is_kept():
	rows = accounts()
	cash = next(r for r in rows if r["account_number"] == "111")
	cash["account_category"] = "Mine"
	changes, _, kept = plan_assignment(rows, TABLE, "A")
	assert kept == [(cash["name"], "Mine", "Tiền và tương đương tiền")]
	assert cash["name"] not in {name for name, _, _ in changes}
	same = dict(cash, account_category="Tiền và tương đương tiền")
	assert plan_assignment([same], TABLE, "A") == ([], [], [])


def test_accounts_of_another_company_are_never_touched():
	rows = accounts()
	other = [dict(r, company="B", name="B " + r["name"], account_category="Theirs") for r in rows]
	changes, unplaced, kept = plan_assignment(rows + other, TABLE, "A")
	touched = {name for name, _, _ in changes} | set(unplaced) | {name for name, _, _ in kept}
	assert touched
	assert not any(name.startswith("B ") for name in touched)


def test_existing_categories_with_another_root_type_are_conflicts():
	existing = {"Tiền và tương đương tiền": "Asset", "Phải trả người bán": "Asset"}
	missing, conflicts = category_conflicts(DATA["categories"], existing)
	assert len(missing) == len(DATA["categories"]) - 2
	assert len(conflicts) == 1 and "Phải trả người bán" in conflicts[0]
