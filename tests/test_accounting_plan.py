"""Tests for plan.py and chart.decide: what the actions decide from the facts setup.py collects. No site."""

import pytest

from erpcm.vn.accounting import chart, plan

TT99 = chart.load_chart()["tree"]


def rows_from(tree, abbr="A", company="A"):
	"""The Account rows create_charts would leave for `tree`."""
	rows = []

	def walk(node, parent_docname, root_type):
		for name, child in node.items():
			if name in chart.CHART_META or not isinstance(child, dict):
				continue
			rt = child.get("root_type") if parent_docname is None else root_type
			number = child.get("account_number") or ""
			dn = plan.docname(number, name, abbr)
			rows.append(
				{
					"name": dn,
					"company": company,
					"account_name": name,
					"account_number": number,
					"parent_account": parent_docname,
					"account_type": child.get("account_type"),
					"root_type": rt,
					"is_group": chart.is_group(child),
				}
			)
			walk(child, dn, rt)

	walk(tree, None, None)
	return rows


WIZARD = {
	"Application of Funds (Assets)": {
		"root_type": "Asset",
		"Current Assets": {"Cash In Hand": {"Cash": {"account_type": "Cash"}}},
	},
}


@pytest.mark.parametrize(
	"accounts, style, verdict",
	[
		(0, None, "BUILD"),
		(189, "vi_en", "MATCH"),
		(189, "vi", "MATCH"),
		(95, None, "DIFFERENT"),
		(1, None, "DIFFERENT"),
	],
)
def test_decide(accounts, style, verdict):
	assert chart.decide(accounts, style) == verdict


@pytest.mark.parametrize("style", chart.NAME_STYLES)
def test_a_tt99_chart_in_either_name_style_is_recognised(style):
	assert plan.tt99_style(TT99, rows_from(chart.with_names(TT99, style))) == style


def test_another_chart_or_no_chart_is_not_tt99():
	assert plan.tt99_style(TT99, rows_from(WIZARD)) is None
	assert plan.tt99_style(TT99, []) is None
	rows = rows_from(TT99)
	rows.append(dict(rows[-1], name="9111 - Phụ - A", account_name="Phụ", account_number="9111"))
	assert plan.tt99_style(TT99, rows) is None, "an added account"
	rows = rows_from(TT99)
	rows[5]["account_type"] = "Bank"
	assert plan.tt99_style(TT99, rows) is None, "a retyped account"


def test_two_accounts_with_the_same_key_are_never_tt99():
	rows = rows_from(TT99)
	rows.append(dict(rows[-1], name="911 bis - A"))
	flat, duplicates = plan.live_flat(rows)
	assert duplicates == sorted([rows[-2]["name"], "911 bis - A"])
	assert len(flat) == len(rows) - 1
	assert plan.tt99_style(TT99, rows) is None
	assert plan.tt99_style(TT99, rows[:-1]) == "vi_en"


def test_a_long_abbreviation_does_not_fit_the_bilingual_names():
	problem = plan.name_length_problem(TT99, "ABCDEFGHIJ", 140)
	assert problem and "names='vi'" in problem
	assert plan.name_length_problem(chart.with_names(TT99, "vi"), "ABCDEFGHIJ", 140) is None
	assert plan.name_length_problem(TT99, "ABC", 140) is None
	longest = plan.longest_docname(TT99, "A")
	assert plan.name_length_problem(TT99, "A", len(longest)) is None
	assert plan.name_length_problem(TT99, "A", len(longest) - 1)


def test_may_write_needs_the_tt99_chart_and_no_posting():
	assert plan.may_write(None, {})
	assert plan.may_write("vi", {}) == []
	for doctype in plan.POSTING_DOCTYPES:
		assert plan.may_write("vi_en", {doctype: 1})
	assert plan.may_write("vi_en", {"GL Entry": 0}) == []


LEDGERS = [
	{"name": "111 - Tiền mặt - A", "account_number": "111"},
	{"name": "1121 - Tiền gửi VND - A", "account_number": "1121"},
	{"name": "131 - Phải thu - A", "account_number": "131"},
]


def test_defaults_fill_empty_and_invalid_fields_and_keep_a_chosen_ledger():
	mapping = {
		"default_cash_account": "111",
		"default_receivable_account": "131",
		"default_bank_account": "1121",
	}
	current = {
		"default_cash_account": "1121 - Tiền gửi VND - A",  # a person chose another ledger
		"default_receivable_account": "Debtors - A",  # left over from another chart
		"default_bank_account": None,
	}
	changes, kept, missing = plan.plan_defaults(mapping, LEDGERS, current)
	assert changes == {
		"default_receivable_account": "131 - Phải thu - A",
		"default_bank_account": "1121 - Tiền gửi VND - A",
	}
	assert kept == [
		{"field": "default_cash_account", "current": "1121 - Tiền gửi VND - A", "chart": "111 - Tiền mặt - A"}
	]
	assert missing == []


def test_defaults_report_a_number_without_exactly_one_ledger():
	changes, kept, missing = plan.plan_defaults({"round_off_account": "6428"}, LEDGERS, {})
	assert changes == {} and kept == []
	assert missing == ["round_off_account: 0 tài khoản chi tiết số 6428"]
	two = LEDGERS + [{"name": "111 - Khác - A", "account_number": "111"}]
	assert plan.plan_defaults({"default_cash_account": "111"}, two, {})[2]


def test_the_shipped_defaults_resolve_on_a_built_tt99_company():
	import json

	with open(chart.DATA + "/tt99_company_defaults.json", encoding="utf-8") as f:
		mapping = json.load(f)["defaults"]
	ledgers = [r for r in rows_from(TT99) if not r["is_group"]]
	changes, kept, missing = plan.plan_defaults(mapping, ledgers, {})
	assert missing == [] and kept == []
	assert len(changes) == len(mapping) == 16
