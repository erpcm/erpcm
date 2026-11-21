"""setup.py against the in-memory Frappe of fake_frappe.py: behaviour, not call order. No site.

The fake's rollback really restores every table, its write counter really counts, its name lookups
compare like MariaDB's collation, and its Company insert honours ERPNext's chart flag. What it cannot
show (real SQL, ERPNext's validations, nested sets) rests on tools/bench.
"""

import importlib
import sys

import pytest
from fake_frappe import install, norm

from erpcm.vn.accounting import chart, plan

TT99 = chart.load_chart()["tree"]


@pytest.fixture
def env(monkeypatch):
	frappe, site = install(monkeypatch)
	s = importlib.import_module("erpcm.vn.accounting.setup")
	yield s, frappe, site
	sys.modules.pop("erpcm.vn.accounting.setup", None)


def tables(site):
	return {dt: dict(rows) for dt, rows in site.tables.items()}


def test_a_company_is_created_with_the_tt99_chart_categories_and_defaults(env):
	s, frappe, site = env
	r = s.create_company("Công Ty Mới", "CTM")
	assert r["verdict"] == "CREATED"
	assert r["accounts"] == 189
	assert plan.tt99_style(TT99, s._rows("Công Ty Mới")) == "vi_en"
	assert len(r["categories_created"]) == 38
	assert len(r["defaults_set"]) == 16
	assert len(site.tables["Warehouse"]) == 5
	assert frappe.local.flags.ignore_chart_of_accounts is None and frappe.flags.in_import is False


@pytest.mark.parametrize("before", [None, False, True])
def test_the_chart_flag_and_in_import_come_back_after_a_failure(env, before):
	s, frappe, site = env
	frappe.local.flags.ignore_chart_of_accounts = before
	start = tables(site)
	site.drop_account = "111 - Tiền mặt / Cash on Hand - CTM"
	with pytest.raises(Exception):
		s.create_company("Công Ty Mới", "CTM")
	assert frappe.local.flags.ignore_chart_of_accounts is before
	assert frappe.flags.in_import is False
	assert tables(site) == start


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyboardInterrupt()])
def test_any_failure_leaves_nothing_and_clears_the_company_cache(env, monkeypatch, error):
	s, frappe, site = env
	start = tables(site)

	def failing(company):
		raise error

	monkeypatch.setattr(s, "_apply_defaults", failing)
	with pytest.raises(type(error)):
		s.create_company("Công Ty Mới", "CTM")
	assert tables(site) == start
	assert ("Company", "Công Ty Mới") in site.cleared


def test_the_build_is_checked(env):
	s, frappe, site = env
	start = tables(site)
	site.drop_account = "911 - Xác định kết quả kinh doanh / Income Summary - CTM"
	with pytest.raises(frappe.ValidationError):
		s.create_company("Công Ty Mới", "CTM")
	assert tables(site) == start


def test_a_chart_erpnext_built_despite_the_flag_stops_the_creation(env):
	s, frappe, site = env
	start = tables(site)
	site.flag_ignored = True
	with pytest.raises(frappe.ValidationError, match="ignore_chart_of_accounts"):
		s.create_company("Công Ty Mới", "CTM")
	assert tables(site) == start


def test_create_permission_is_required_before_anything_is_looked_up(env):
	s, frappe, site = env
	frappe.denied.add("create")
	with pytest.raises(frappe.PermissionError):
		s.create_company("Công Ty Mới", "CTM")
	assert frappe.db.lookups == []


@pytest.mark.parametrize(
	"name, abbr, why",
	[
		("cong ty moi", "XYZ", "Đã có công ty"),
		("CÔNG TY MỚI ", "XYZ", "Đã có công ty"),
		("Công Ty Khác", "ctm", "Viết tắt"),
		("Công Ty Khác", "C-M", "chữ và số"),
		("X" * 136, "XY", "tên công ty quá dài"),
		("Công Ty Khác", "ABCDEFGHIJ", "names='vi'"),
	],
)
def test_existing_names_and_bad_input_refuse_without_writing(env, name, abbr, why):
	s, frappe, site = env
	assert s.create_company("Công Ty Mới", "CTM")["verdict"] == "CREATED"
	frappe.db.commit()
	start = tables(site)
	r = s.create_company(name, abbr)
	assert r["verdict"] == "REFUSE"
	assert any(why in x for x in r["reasons"]), r["reasons"]
	assert tables(site) == start


def test_a_category_the_site_has_under_another_spelling_is_reused_or_refuses(env):
	s, frappe, site = env
	frappe.db.write("Account Category", {"name": "PHẢI TRẢ NGƯỜI BÁN", "root_type": "Asset"})
	frappe.db.commit()
	r = s.create_company("Công Ty Mới", "CTM")
	assert r["verdict"] == "REFUSE" and "PHẢI TRẢ NGƯỜI BÁN" in r["reasons"][0]

	site.tables["Account Category"]["PHẢI TRẢ NGƯỜI BÁN"]["root_type"] = "Liability"
	frappe.db.commit()
	r = s.create_company("Công Ty Mới", "CTM")
	assert r["verdict"] == "CREATED"
	assert len(r["categories_created"]) == 37
	payable = next(a for a in site.tables["Account"].values() if a["account_number"] == "331")
	assert payable["account_category"] == "PHẢI TRẢ NGƯỜI BÁN"


def test_a_build_that_could_reach_the_write_limit_refuses(env):
	s, frappe, site = env
	frappe.conf["max_writes_per_transaction"] = 900
	start = tables(site)
	r = s.create_company("Công Ty Mới", "CTM")
	assert r["verdict"] == "REFUSE" and any("max_writes_per_transaction" in x for x in r["reasons"])
	assert tables(site) == start


def test_writes_already_in_the_transaction_or_transaction_control_off_refuse(env):
	s, frappe, site = env
	frappe.db.transaction_writes = 1
	with pytest.raises(frappe.ValidationError):
		s.create_company("Công Ty Mới", "CTM")
	frappe.db.transaction_writes = 0
	frappe.db._disable_transaction_control = 1
	with pytest.raises(frappe.ValidationError):
		s.create_company("Công Ty Mới", "CTM")
	assert site.tables["Company"] == {}


def test_the_company_is_used_by_its_stored_name(env):
	s, frappe, site = env
	s.create_company("Công Ty Mới", "CTM")
	r = s.chart_status("cong ty moi ")
	assert r["company"] == "Công Ty Mới" and r["verdict"] == "MATCH"


def test_an_unknown_or_unreadable_company_is_the_same_403(env):
	s, frappe, site = env
	s.create_company("Công Ty Mới", "CTM")
	with pytest.raises(frappe.PermissionError):
		s.chart_status("Không Có")
	frappe.denied.add("read")
	with pytest.raises(frappe.PermissionError):
		s.chart_status("Công Ty Mới")


def test_with_frappe_hr_saving_the_company_later_creates_no_account(env):
	s, frappe, site = env
	site.apps.append("hrms")
	for claim_type in ("Travel", "Food"):
		site.tables["Expense Claim Type"][claim_type] = {"name": claim_type}
	site.tables["Expense Claim Account"]["Travel-Other"] = {
		"name": "Travel-Other",
		"parent": "Travel",
		"company": "Other",
		"default_account": "Theirs",
	}
	frappe.db.commit()
	r = s.create_company("Công Ty Mới", "CTM")
	assert r["verdict"] == "CREATED"
	assert sorted(r["expense_claim_types"]) == ["Food", "Travel"]
	assert site.tables["Expense Claim Account"]["Travel-Other"]["default_account"] == "Theirs"
	ours = [x for x in site.tables["Expense Claim Account"].values() if x["company"] == "Công Ty Mới"]
	assert all(x["default_account"].startswith("6428 ") for x in ours) and len(ours) == 2
	company = site.tables["Company"]["Công Ty Mới"]
	assert company["default_payroll_payable_account"].startswith("334 ")
	assert company["default_employee_advance_account"].startswith("141 ")

	frappe.get_doc("Company", "Công Ty Mới").save()  # the Company form saved later, chart flag off
	assert s.chart_status("Công Ty Mới")["verdict"] == "MATCH"


def test_setup_chart_builds_only_on_a_company_without_accounts(env):
	s, frappe, site = env
	frappe.db.write("Company", {"name": "Trống", "company_name": "Trống", "abbr": "TR"})
	frappe.db.commit()
	assert s.setup_chart("Trống")["verdict"] == "BUILT"
	frappe.db.commit()
	start = tables(site)
	assert s.setup_chart("Trống")["verdict"] == "MATCH"
	frappe.db.write("Company", {"name": "Khác", "company_name": "Khác", "abbr": "KH"})
	frappe.db.write(
		"Account", {"name": "Cash - KH", "company": "Khác", "account_name": "Cash", "is_group": 0}
	)
	frappe.db.commit()
	start = tables(site)
	assert s.setup_chart("Khác")["verdict"] == "DIFFERENT"
	assert tables(site) == start


@pytest.mark.parametrize("action", ["apply_account_categories", "set_company_defaults"])
def test_the_repairs_need_the_tt99_chart_and_no_posting(env, action):
	s, frappe, site = env
	frappe.db.write("Company", {"name": "Khác", "company_name": "Khác", "abbr": "KH"})
	frappe.db.write(
		"Account", {"name": "Cash - KH", "company": "Khác", "account_name": "Cash", "is_group": 0}
	)
	frappe.db.commit()
	start = tables(site)
	assert getattr(s, action)("Khác")["verdict"] == "REFUSE"
	assert tables(site) == start

	s.create_company("Công Ty Mới", "CTM")
	frappe.db.write("GL Entry", {"name": "GLE-1", "company": "Công Ty Mới"})
	frappe.db.commit()
	start = tables(site)
	assert getattr(s, action)("Công Ty Mới")["verdict"] == "REFUSE"
	assert tables(site) == start


def test_the_fake_compares_names_like_the_database():
	assert norm("Công Ty Mới ") == norm("cong ty moi")
	assert norm("Đ") != norm("d")  # MariaDB 11.8: 'đ' = 'd' collate utf8mb4_unicode_ci is 0


def test_vietnamese_names_and_country_whatever_the_config_says(env):
	s, frappe, site = env
	frappe.conf["country"] = "Italy"
	r = s.create_company("Công Ty Việt", "CTV", names="vi")
	assert r["verdict"] == "CREATED"
	assert s.chart_status("Công Ty Việt")["style"] == "vi"
	assert site.tables["Company"]["Công Ty Việt"]["country"] == "Vietnam"


def test_setup_chart_refuses_a_company_with_postings_but_no_account(env):
	s, frappe, site = env
	frappe.db.write("Company", {"name": "Trống", "company_name": "Trống", "abbr": "TR"})
	frappe.db.write("GL Entry", {"name": "GLE-1", "company": "Trống"})
	frappe.db.commit()
	start = tables(site)
	assert s.setup_chart("Trống")["verdict"] == "REFUSE"
	assert tables(site) == start


def test_the_defaults_repair_adds_no_second_expense_claim_row(env):
	s, frappe, site = env
	site.apps.append("hrms")
	site.tables["Expense Claim Type"]["Travel"] = {"name": "Travel"}
	frappe.db.commit()
	s.create_company("Công Ty Mới", "CTM")
	frappe.db.commit()
	rows = len(site.tables["Expense Claim Account"])
	r = s.set_company_defaults("Công Ty Mới")
	assert r["verdict"] == "MATCH" and r["expense_claim_types"] == []
	assert len(site.tables["Expense Claim Account"]) == rows


def test_a_failure_inside_create_charts_restores_erpnexts_flags(env):
	s, frappe, site = env
	start = tables(site)
	site.fail_in_build = True
	with pytest.raises(RuntimeError):
		s.create_company("Công Ty Mới", "CTM")
	assert frappe.local.flags.ignore_update_nsm is False
	assert frappe.db.auto_commit_on_many_writes == 0
	assert tables(site) == start
	assert ("*", None) in site.cleared, "the whole cache is cleared before the rollback"


def test_a_successful_build_leaves_erpnexts_switches_as_they_were(env):
	s, frappe, site = env
	s.create_company("Công Ty Mới", "CTM")
	assert frappe.db.auto_commit_on_many_writes == 0
	assert frappe.local.flags.ignore_update_nsm is False
	assert [r["company"] for r in site.tables["Mode of Payment Account"].values()] == ["Công Ty Mới"]


def test_the_write_limit_counts_the_accounts_of_the_whole_site(env):
	s, frappe, site = env
	for i in range(400):
		frappe.db.write("Account", {"name": f"Other {i}", "company": "Other", "account_name": f"Other {i}"})
	frappe.db.commit()
	frappe.conf["max_writes_per_transaction"] = 1500  # 400 x 2 + 1000 = 1800 would pass it
	assert s.create_company("Công Ty Mới", "CTM")["verdict"] == "REFUSE"
	frappe.db.write("Company", {"name": "Trống", "company_name": "Trống", "abbr": "TR"})
	frappe.db.commit()
	r = s.setup_chart("Trống")
	assert r["verdict"] == "REFUSE" and any("max_writes_per_transaction" in x for x in r["reasons"])
	assert not s._rows("Trống")


def test_a_company_whose_name_differs_from_its_docname_is_found(env):
	s, frappe, site = env
	frappe.db.write("Company", {"name": "Đổi Tên", "company_name": "Công Ty Cũ", "abbr": "CC"})
	frappe.db.commit()
	r = s.create_company("cong ty cu", "XYZ")
	assert r["verdict"] == "REFUSE" and "Đã có công ty" in r["reasons"][0]


def test_without_account_category_root_type_nothing_is_created(env):
	s, frappe, site = env
	site.missing_fields.add(("Account Category", "root_type"))
	r = s.create_company("Công Ty Mới", "CTM")
	assert r["verdict"] == "REFUSE" and site.tables["Company"] == {}


def test_defaults_are_not_written_when_one_account_is_missing(env, monkeypatch):
	s, frappe, site = env
	real = s.load_company_defaults

	def with_a_missing_number():
		data = real()
		data["defaults"] = dict(data["defaults"], default_bank_account="1129")
		return data

	monkeypatch.setattr(s, "load_company_defaults", with_a_missing_number)
	start = tables(site)
	with pytest.raises(frappe.ValidationError, match="1129"):
		s.create_company("Công Ty Mới", "CTM")
	assert tables(site) == start

	monkeypatch.setattr(s, "load_company_defaults", real)
	s.create_company("Công Ty Mới", "CTM")
	company = site.tables["Company"]["Công Ty Mới"]
	company["default_cash_account"] = None
	frappe.db.commit()
	monkeypatch.setattr(s, "load_company_defaults", with_a_missing_number)
	r = s.set_company_defaults("Công Ty Mới")
	assert r["verdict"] == "REFUSE" and "1129" in r["reasons"][0]
	assert site.tables["Company"]["Công Ty Mới"]["default_cash_account"] is None


def _hr_site(site, frappe):
	site.apps.append("hrms")
	for claim_type in ("Travel", "Food"):
		site.tables["Expense Claim Type"][claim_type] = {"name": claim_type}
	site.tables["Expense Claim Account"]["Travel-Other"] = {
		"name": "Travel-Other",
		"parent": "Travel",
		"company": "Other",
		"default_account": "Theirs",
	}
	frappe.db.commit()


def test_frappe_hr_installed_after_the_company_and_postings_has_a_way_out(env):
	s, frappe, site = env
	s.create_company("Công Ty Mới", "CTM")
	frappe.db.write("GL Entry", {"name": "GLE-1", "company": "Công Ty Mới"})
	company = site.tables["Company"]["Công Ty Mới"]
	company["round_off_account"] = None  # a non-HR default that must stay as it is
	frappe.db.commit()
	assert s.set_company_defaults("Công Ty Mới")["verdict"] == "REFUSE", "posted, and no Frappe HR"

	_hr_site(site, frappe)
	other = dict(site.tables["Expense Claim Account"]["Travel-Other"])
	r = s.set_company_defaults("Công Ty Mới")
	assert r["verdict"] == "CHANGED" and "Frappe HR" in r["scope"]
	assert set(r["set"]) == {"default_payroll_payable_account", "default_employee_advance_account"}
	assert sorted(r["expense_claim_types"]) == ["Food", "Travel"]
	assert company["round_off_account"] is None
	assert site.tables["Expense Claim Account"]["Travel-Other"] == other
	frappe.get_doc("Company", "Công Ty Mới").save()
	assert s.chart_status("Công Ty Mới")["verdict"] == "MATCH"


def test_the_hr_way_out_does_not_overwrite_a_filled_hr_field(env):
	s, frappe, site = env
	_hr_site(site, frappe)
	s.create_company("Công Ty Mới", "CTM")
	company = site.tables["Company"]["Công Ty Mới"]
	company["default_employee_advance_account"] = "131 - Phải thu của khách hàng / Trade Receivables - CTM"
	frappe.db.write("GL Entry", {"name": "GLE-1", "company": "Công Ty Mới"})
	frappe.db.commit()
	r = s.set_company_defaults("Công Ty Mới")
	assert r["verdict"] == "MATCH" and r["set"] == {}
	assert company["default_employee_advance_account"].startswith("131 ")


def test_the_hr_way_out_fills_only_empty_fields_and_adds_no_mode_of_payment_row(env):
	s, frappe, site = env
	_hr_site(site, frappe)
	s.create_company("Công Ty Mới", "CTM")
	company = site.tables["Company"]["Công Ty Mới"]
	company["default_employee_advance_account"] = (
		"1 - Tài sản ngắn hạn / Current Assets - CTM"  # a group: not ours to fix
	)
	company["default_payroll_payable_account"] = None
	site.tables["Mode of Payment Account"].clear()
	frappe.db.write("GL Entry", {"name": "GLE-1", "company": "Công Ty Mới"})
	frappe.db.commit()
	r = s.set_company_defaults("Công Ty Mới")
	assert set(r["set"]) == {"default_payroll_payable_account"}
	assert company["default_employee_advance_account"].startswith("1 - ")
	assert site.tables["Mode of Payment Account"] == {}


def test_without_frappe_hr_nothing_of_frappe_hr_is_touched(env):
	s, frappe, site = env
	r = s.create_company("Công Ty Mới", "CTM")
	assert r["verdict"] == "CREATED" and r["expense_claim_types"] == []
	assert "default_payroll_payable_account" not in site.tables["Company"]["Công Ty Mới"]
