"""Tests for the TT99 chart data and the pure decisions taken on it. No site, no database, no network.

These prove the chart is internally consistent and usable by ERPNext. They do NOT prove it matches the
circular: that needs tt99_appendix_ii.json, transcribed by a person from the official text. Until that
file exists, the comparison test is skipped and says so.
"""

import json
import os
import re

import pytest

from erpcm.vn.accounting import chart
from erpcm.vn.accounting.categories import load_categories

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPENDIX = os.path.join(chart.DATA, "tt99_appendix_ii.json")
DEFAULTS = os.path.join(chart.DATA, "tt99_company_defaults.json")

DATA = chart.load_chart()
TREE = DATA["tree"]
NODES = list(chart.iter_nodes(TREE))


def leaves():
	return [(p, n, node, rt) for p, n, node, rt in NODES if not chart.is_group(node)]


def test_numbers_are_unique():
	seen = [str(node["account_number"]) for _, _, node, _ in NODES if node.get("account_number")]
	assert len(seen) == len(set(seen)), sorted({n for n in seen if seen.count(n) > 1})


def test_a_numbered_child_extends_its_parents_number():
	bad = []

	def walk(node, ancestor):
		for name, child in node.items():
			if name in chart.CHART_META or not isinstance(child, dict):
				continue
			number = str(child.get("account_number") or "")
			if number and ancestor and not (number.startswith(ancestor) and number != ancestor):
				bad.append((ancestor, number, name))
			walk(child, number or ancestor)

	walk(TREE, "")
	assert not bad, bad


def test_six_roots_each_with_a_root_type():
	roots = [(name, node.get("root_type")) for parent, name, node, _ in NODES if parent is None]
	assert len(roots) == 6, roots
	for name, root_type in roots:
		assert root_type in chart.ROOT_TYPES, (name, root_type)
	assert {rt for _, rt in roots} == chart.ROOT_TYPES


def test_911_sits_under_an_equity_root():
	hits = [(node, rt) for _, _, node, rt in NODES if str(node.get("account_number")) == "911"]
	assert len(hits) == 1
	node, root_type = hits[0]
	assert root_type == "Equity"
	assert not chart.is_group(node), "Period Closing Voucher refuses a group as closing account"


def test_account_types_come_from_a_fixed_allowed_set():
	# The set is Account.account_type's options on ERPNext v16.55, checked on a bench.
	assert len(chart.ACCOUNT_TYPES) == 31
	used = {node["account_type"] for _, _, node, _ in NODES if node.get("account_type")}
	assert used, "the chart types its accounts"
	assert used <= chart.ACCOUNT_TYPES, used - chart.ACCOUNT_TYPES


def test_flatten_keys_are_unique():
	flat = chart.flatten(TREE)
	assert len(flat) == len(NODES) == 189
	# Names repeat under different parents; the (parent, name) key is what keeps them apart.
	names = [name for _, name, _, _ in NODES]
	assert len(set(names)) < len(names)


def test_every_addition_exists_in_the_tree():
	additions = DATA["additions"]
	assert additions
	names = {name for _, name, _, _ in NODES}
	for entry in additions:
		if entry.get("number"):
			hit = chart.find(TREE, entry["number"])
			assert hit, entry
			if entry["kind"] == "account_type":
				assert hit[1].get("account_type") == entry["account_type"], entry
		else:
			assert entry["name"] in names, entry
		assert entry["kind"] in {"root", "group", "account", "account_type"}, entry
		assert entry.get("reason"), entry


def test_chart_minus_additions_equals_the_transcribed_appendix():
	if not os.path.exists(APPENDIX):
		pytest.skip(
			"tt99_appendix_ii.json does not exist yet: the chart has not been compared with the text of "
			"Appendix II of Circular 99/2025/TT-BTC"
		)
	with open(APPENDIX, encoding="utf-8") as f:
		transcribed = {str(a["number"]) for a in json.load(f)["accounts"]}
	added = {str(e["number"]) for e in DATA["additions"] if e.get("number") and e["kind"] != "account_type"}
	ours = chart.numbers(TREE) - added
	assert ours == transcribed, {
		"only in chart": sorted(ours - transcribed),
		"only in text": sorted(transcribed - ours),
	}


def test_flatten_keeps_every_field_and_inherits_the_root_type():
	tree = {
		"Root": {
			"root_type": "Asset",
			"Group": {"account_number": "1", "Leaf": {"account_number": "11", "account_type": "Cash"}},
			"Empty group": {"is_group": 1},
		}
	}
	assert chart.flatten(tree) == {
		(None, "Root"): (None, None, "Asset", 1),
		("Root", "Group"): ("1", None, "Asset", 1),
		("Group", "Leaf"): ("11", "Cash", "Asset", 0),
		("Root", "Empty group"): (None, None, "Asset", 1),
	}


def test_diff_reports_a_changed_value_under_the_same_key():
	want = {(None, "A"): ("1", "Cash", "Asset", 0)}
	have = {(None, "A"): ("1", "Bank", "Asset", 0)}
	assert chart.diff(want, have) == [((None, "A"), ("1", "Cash", "Asset", 0), ("1", "Bank", "Asset", 0))]


def test_vietnamese_names_refuse_to_merge_two_siblings():
	tree = {"Gốc / Root": {"root_type": "Asset", "Tiền / Cash": {}, "Tiền / Money": {}}}
	with pytest.raises(ValueError):
		chart.with_names(tree, "vi")


def test_validate_chart_accepts_the_data_and_names_each_fault():
	assert chart.validate_chart(TREE) == []

	def broken(change):
		tree = json.loads(json.dumps(TREE))
		change(tree)
		return chart.validate_chart(tree)

	assets = "Tài sản / Assets"
	current = "Tài sản ngắn hạn / Current Assets"
	assert broken(lambda t: t[assets][current]["Tiền mặt / Cash on Hand"].update(account_number="112"))
	assert broken(lambda t: t[assets][current]["Tiền mặt / Cash on Hand"].update(account_number="211"))
	assert broken(lambda t: t[assets][current]["Tiền mặt / Cash on Hand"].update(account_type="Petty Cash"))
	assert broken(lambda t: t[assets].pop("root_type"))
	assert broken(lambda t: t["Xác định kết quả kinh doanh / Income Summary"].update(root_type="Income"))


def test_vietnamese_only_names_keep_every_account():
	vi = chart.with_names(TREE, "vi")
	assert len(chart.flatten(vi)) == len(NODES)
	assert chart.validate_chart(vi) == []
	assert "Tiền mặt" in vi["Tài sản"]["Tài sản ngắn hạn"]
	with pytest.raises(ValueError):
		chart.with_names(TREE, "en")


def test_diff_names_what_is_missing_on_each_side():
	want = {(None, "A"): (None, None, "Asset", 1), ("A", "B"): ("1", None, "Asset", 0)}
	have = {(None, "A"): (None, None, "Asset", 1), ("A", "C"): ("2", None, "Asset", 0)}
	assert chart.diff(want, want) == []
	assert chart.diff(want, have) == [
		(("A", "B"), ("1", None, "Asset", 0), None),
		(("A", "C"), None, ("2", None, "Asset", 0)),
	]


def test_company_defaults_point_at_ledger_accounts_of_the_chart():
	with open(DEFAULTS, encoding="utf-8") as f:
		defaults = json.load(f)["defaults"]
	for field, number in defaults.items():
		hit = chart.find(TREE, number)
		assert hit, (field, number)
		assert not chart.is_group(hit[1]), (field, number)


def test_counts_quoted_in_the_readme_equal_the_data():
	with open(os.path.join(REPO, "README.md"), encoding="utf-8") as f:
		readme = " ".join(f.read().split())  # sentences wrap across lines
	m = re.search(r"(\d+) tài khoản \((\d+) tài khoản chi tiết, (\d+) tài khoản tổng hợp\)", readme)
	assert m, "README must state the chart's size"
	total, ledgers, groups = map(int, m.groups())
	assert total == len(NODES)
	assert ledgers == len(leaves())
	assert groups == len(NODES) - len(leaves())

	m = re.search(r"(\d+) mục bổ sung", readme)
	assert m and int(m.group(1)) == len(DATA["additions"])

	m = re.search(r"(\d+) nhóm tài khoản \(Account Category\)", readme)
	assert m and int(m.group(1)) == len(load_categories()["categories"])

	with open(DEFAULTS, encoding="utf-8") as f:
		defaults = json.load(f)["defaults"]
	m = re.search(r"(\d+) ô tài khoản mặc định của Company", readme)
	assert m and int(m.group(1)) == len(defaults)
