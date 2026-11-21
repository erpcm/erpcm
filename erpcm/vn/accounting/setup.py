"""Create a company with the TT99 chart, and read or repair one. Where the pure modules meet Frappe.

    create_company(company_name, abbr, ...)  a NEW Vietnamese Company with the TT99 chart, its account
                                            categories and default accounts, in one transaction
    chart_status(company)                   read only: MATCH (and which name style), BUILD, or DIFFERENT
    setup_chart(company)                    build the TT99 chart on a company that has no account at all
    apply_account_categories(company)       repair: Account Category on a TT99 company's ledger accounts
    set_company_defaults(company)           repair: the Company's default-account fields

ERPCM never replaces an existing chart. Deleting accounts on a live ERPNext site cannot be made safe from
inside an app: ERPNext posts to the ledger without any locking read on Company or Account, so a request
that read an account before the replacement can post to it afterwards. A company that already has a
chart keeps it; a TT99 company is created new.

Nothing runs at install or migrate. None of the actions commits: `bench execute` commits when the call
returns, a POST request when it ends. Each writing action refuses to start inside a transaction that has
already written, or where Frappe has switched transaction control off, or when building the chart could
reach the site's write limit (past which Frappe commits in the middle), so that a failure rolls back
exactly its own work.
"""

import json
import os

import frappe
from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts
from frappe import _
from frappe.utils import cint

from erpcm.vn.accounting import plan
from erpcm.vn.accounting.categories import category_conflicts, load_categories, plan_assignment, prefix_table
from erpcm.vn.accounting.chart import DATA, NAME_STYLES, decide, diff, flatten, load_chart, with_names

ROLES = ("System Manager", "Accounts Manager")

# The chart is Vietnamese, and for some other countries ERPNext's regional setup commits mid-call.
COUNTRY = "Vietnam"

DEFAULTS_FILE = os.path.join(DATA, "tt99_company_defaults.json")

ACCOUNT_FIELDS = [
	"name",
	"company",
	"account_name",
	"account_number",
	"parent_account",
	"account_type",
	"root_type",
	"is_group",
	"account_category",
]


def _require_company(company, ptype):
	"""The stored name of the Company `company` names. One answer, 403, for a company that does not
	exist and for one the caller may not see, so the error does not tell which companies exist."""
	if not isinstance(company, str) or not company.strip():
		frappe.throw(_("Thiếu tên công ty (company)"))
	name = frappe.db.get_value("Company", company, "name")
	if not name or not frappe.has_permission("Company", ptype, name):
		frappe.throw(
			_("Không có công ty {0}, hoặc bạn không có quyền {1} trên nó").format(repr(company), ptype),
			frappe.PermissionError,
		)
	return name


def _require_names(names):
	if names not in NAME_STYLES:
		frappe.throw(_("names phải là 'vi' hoặc 'vi_en', không phải {0}").format(repr(names)))


def _require_text(value, label):
	if not isinstance(value, str) or not value.strip():
		frappe.throw(_("Thiếu {0}").format(label))
	return value.strip()


def _write_limit():
	return cint(frappe.conf.get("max_writes_per_transaction")) or frappe.db.MAX_WRITES_PER_TRANSACTION


def _require_clean_transaction():
	"""A failure must roll back only this action's work: no earlier writes, transaction control on."""
	if getattr(frappe.db, "_disable_transaction_control", 0):
		frappe.throw(
			_(
				"ERPCM không chạy khi Frappe đang tắt điều khiển giao dịch (ví dụ trong một doc_events hay "
				"Server Script): lỗi giữa chừng khi đó không rollback được."
			)
		)
	if frappe.db.transaction_writes:
		frappe.throw(
			_(
				"Giao dịch hiện tại đã có {0} lệnh ghi chưa commit; ERPCM chỉ chạy trong một giao dịch chưa "
				"ghi gì, để lỗi giữa chừng không kéo theo phần việc của bên gọi."
			).format(frappe.db.transaction_writes)
		)


def _forget(company):
	"""After any failure, KeyboardInterrupt and lost connections included: forget what the attempt put in
	the caches, then roll back. Caches first, so a rollback that itself fails cannot leave them behind."""
	names = {}
	try:
		for doctype in ("Account", "Warehouse", "Cost Center", "Department"):
			names[doctype] = frappe.get_all(doctype, filters={"company": company}, pluck="name")
	except BaseException:
		pass
	try:
		frappe.clear_document_cache("Company", company)
		for doctype, docnames in names.items():
			for docname in docnames:
				frappe.clear_document_cache(doctype, docname)
		frappe.clear_cache()
	finally:
		try:
			frappe.db.rollback()
		except BaseException:
			pass  # the connection is gone; the server rolls the transaction back itself


def _rows(company):
	return [
		dict(r)
		for r in frappe.get_all(
			"Account", filters={"company": company}, fields=ACCOUNT_FIELDS, order_by="name"
		)
	]


def _posted(company):
	return {dt: n for dt in plan.POSTING_DOCTYPES if (n := frappe.db.count(dt, {"company": company}))}


def _max_name_length():
	return frappe.db.sql(
		"""select character_maximum_length from information_schema.columns
		where table_schema = database() and table_name = 'tabAccount' and column_name = 'name'"""
	)[0][0]


def _categories_supported():
	return frappe.get_meta("Account Category").has_field("root_type") and frappe.get_meta(
		"Account"
	).has_field("account_category")


def _hrms():
	return "hrms" in frappe.get_installed_apps()


def _build(company, target):
	"""create_charts with the TT99 tree, then check every account is there as the file says."""
	auto_commit, nsm = frappe.db.auto_commit_on_many_writes, frappe.local.flags.ignore_update_nsm
	try:
		create_charts(company, custom_chart=target)
	finally:
		# create_charts switches both on and, when it fails midway, leaves them on
		frappe.db.auto_commit_on_many_writes = auto_commit
		frappe.local.flags.ignore_update_nsm = nsm
	left = diff(flatten(target), plan.live_flat(_rows(company))[0])
	if left:
		frappe.throw(
			_("Dựng hệ thống tài khoản cho {0} xong nhưng còn {1} chỗ khác với tệp: {2}").format(
				company, len(left), left[:5]
			)
		)


def _categories():
	"""(categories, existing): the TT99 categories, each renamed to the spelling already stored on the site
	when the database considers the two names equal, and {name: root_type} of those that exist."""
	categories, existing = [], {}
	for c in load_categories()["categories"]:
		row = frappe.db.get_value("Account Category", c["name"], ["name", "root_type"], as_dict=True)
		if row:
			c = dict(c, name=row.name)
			existing[row.name] = row.root_type
		categories.append(c)
	return categories, existing


def _apply_categories(company, categories, existing):
	missing, _conflicts = category_conflicts(categories, existing)
	changes, unplaced, kept = plan_assignment(_rows(company), prefix_table(categories), company)
	for c in missing:
		frappe.get_doc(
			{
				"doctype": "Account Category",
				"account_category_name": c["name"],
				"root_type": c["root_type"],
				"description": _(
					"Nhóm báo cáo do ERPCM tự đặt, không phải danh mục của Thông tư. Tài khoản: {0}."
				).format(", ".join(c["prefixes"])),
			}
		).insert(ignore_permissions=True)  # the role was checked by the caller
	for name, _current, want in changes:
		frappe.db.set_value("Account", name, "account_category", want, update_modified=False)
	return {
		"categories_created": [c["name"] for c in missing],
		"accounts_changed": [{"account": n, "from": cur, "to": w} for n, cur, w in changes],
		"accounts_kept": [{"account": n, "category": cur, "chart": w} for n, cur, w in kept],
		"unplaced": unplaced,
	}


def load_company_defaults(path=DEFAULTS_FILE):
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def _expense_claim_rows(company, account):
	"""Give every Expense Claim Type a row for THIS company, so Frappe HR finds one and does not create an
	"Expense Claims" account outside the chart when the Company is saved. Other companies' rows untouched."""
	added = []
	for claim_type in frappe.get_all("Expense Claim Type", pluck="name", order_by="name"):
		if frappe.db.exists("Expense Claim Account", {"parent": claim_type, "company": company}):
			continue
		doc = frappe.get_doc("Expense Claim Type", claim_type)
		doc.append("accounts", {"company": company, "default_account": account})
		doc.save(ignore_permissions=True)
		added.append(claim_type)
	return added


def _apply_defaults(company, hr_only=False):
	"""{set, kept, missing, expense_claim_types}. Saves the Company through its own validation when
	something changes. With Frappe HR, its fields are filled and this company's Expense Claim rows added
	before the save, so Frappe HR's on_update creates nothing.

	hr_only: fill only the EMPTY Frappe HR fields and add this company's Expense Claim rows — for a company
	that already posts, where no other default is touched.
	"""
	data = load_company_defaults()
	hrms = {k: v for k, v in data["hrms"].items() if not k.startswith("_")} if _hrms() else {}
	meta = frappe.get_meta("Company")
	mapping = {} if hr_only else dict(data["defaults"])
	mapping.update({f: n for f, n in hrms.items() if f != "expense_claim_account" and meta.has_field(f)})
	doc = frappe.get_doc("Company", company)
	current = {f: doc.get(f) for f in mapping}
	ledgers = [r for r in _rows(company) if not r["is_group"]]
	changes, kept, missing = plan.plan_defaults(mapping, ledgers, current)
	if hr_only:
		kept += [{"field": f, "current": current[f], "chart": a} for f, a in changes.items() if current[f]]
		changes = {f: a for f, a in changes.items() if not current[f]}
	claim_account = None
	if hrms.get("expense_claim_account"):
		found, _k, gone = plan.plan_defaults(
			{"expense_claim_account": hrms["expense_claim_account"]}, ledgers, {}
		)
		missing += gone
		claim_account = found.get("expense_claim_account")
	if missing:
		return {"set": {}, "kept": kept, "missing": missing, "expense_claim_types": []}
	claim_types = _expense_claim_rows(company, claim_account) if claim_account else []
	if changes:
		doc.update(changes)
		doc.save()
	if doc.default_cash_account and not hr_only:
		doc.set_mode_of_payment_account()  # what Company.on_update does when the chart flag is off
	return {"set": changes, "kept": kept, "missing": [], "expense_claim_types": claim_types}


@frappe.whitelist(methods=["POST"])
def create_company(company_name=None, abbr=None, default_currency="VND", names="vi_en"):
	"""Create a NEW Vietnamese Company with the TT99 chart, in one transaction.

	ERPNext's own chart is suppressed (frappe.local.flags.ignore_chart_of_accounts) while the Company is
	inserted; then, in the same transaction: the TT99 chart, the financial report templates ERPNext installs
	for a new company, the default warehouses, the account categories and the default accounts (and, with
	Frappe HR, its default accounts). Refused, with nothing written, when a Company with that name or
	abbreviation exists. Any failure rolls everything back: no Company, no account, no warehouse is left.
	"""
	frappe.only_for(ROLES)
	frappe.has_permission("Company", "create", throw=True)
	company_name = _require_text(company_name, "company_name")
	abbr = _require_text(abbr, "abbr")
	default_currency = _require_text(default_currency, "default_currency")
	_require_names(names)

	tree = with_names(load_chart()["tree"], names)
	max_length = _max_name_length()
	reasons = []
	if frappe.db.exists("Company", company_name) or frappe.db.exists(
		"Company", {"company_name": company_name}
	):
		reasons.append(_("Đã có công ty {0}").format(company_name))
	if frappe.db.exists("Company", {"abbr": abbr}):
		reasons.append(_("Viết tắt {0} đã dùng cho một công ty khác").format(abbr))
	for problem in (
		plan.abbr_problem(abbr),
		plan.company_name_problem(company_name, abbr, max_length),
		plan.name_length_problem(tree, abbr, max_length),
		plan.write_limit_problem(frappe.db.count("Account"), _write_limit()),
	):
		if problem:
			reasons.append(problem)
	if not _categories_supported():
		reasons.append(
			_("Account Category của bản ERPNext này thiếu trường root_type; cần ERPNext 16.55 trở lên")
		)
	categories, existing = _categories()
	reasons += category_conflicts(categories, existing)[1]
	if reasons:
		return {"company": company_name, "verdict": "REFUSE", "reasons": reasons}
	_require_clean_transaction()

	from erpnext.accounts.doctype.financial_report_template.financial_report_template import (
		sync_financial_report_templates,
	)

	flag, in_import = frappe.local.flags.ignore_chart_of_accounts, frappe.flags.in_import
	try:
		frappe.local.flags.ignore_chart_of_accounts = True
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company_name,
				"abbr": abbr,
				"country": COUNTRY,
				"default_currency": default_currency,
				"enable_perpetual_inventory": 1,  # as the setup wizard creates a company
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		).insert()
		if frappe.db.count("Account", {"company": doc.name}):
			frappe.throw(
				_("ERPNext đã tạo tài khoản cho {0} dù cờ ignore_chart_of_accounts").format(doc.name)
			)
		_build(doc.name, tree)
		sync_financial_report_templates()
		doc.reload()
		doc.create_default_warehouses()
		category_result = _apply_categories(doc.name, categories, existing)
		defaults = _apply_defaults(doc.name)
		if defaults["missing"]:
			frappe.throw(_("Thiếu tài khoản cho ô mặc định: {0}").format("; ".join(defaults["missing"])))
		result = {
			"company": doc.name,
			"verdict": "CREATED",
			"names": names,
			"accounts": frappe.db.count("Account", {"company": doc.name}),
			"warehouses": frappe.get_all(
				"Warehouse", filters={"company": doc.name}, pluck="name", order_by="lft"
			),
			"cost_center": frappe.db.get_value("Company", doc.name, "cost_center"),
			**category_result,
			"defaults_set": defaults["set"],
			"expense_claim_types": defaults["expense_claim_types"],
		}
	except BaseException:
		_forget(company_name)
		raise
	finally:
		frappe.local.flags.ignore_chart_of_accounts = flag
		frappe.flags.in_import = in_import  # sync_financial_report_templates sets it
	return result


@frappe.whitelist()
def chart_status(company=None, names="vi_en"):
	"""Where the company's chart stands. Writes nothing."""
	frappe.only_for(ROLES)
	company = _require_company(company, "read")
	_require_names(names)

	tree = load_chart()["tree"]
	rows = _rows(company)
	style = plan.tt99_style(tree, rows)
	result = {
		"company": company,
		"verdict": decide(len(rows), style),
		"style": style,
		"accounts": len(rows),
		"posted": _posted(company),
		"reasons": [],
	}
	if result["verdict"] == "BUILD":
		problem = plan.name_length_problem(
			with_names(tree, names), frappe.db.get_value("Company", company, "abbr"), _max_name_length()
		)
		result["reasons"].append(
			problem or _("Công ty chưa có tài khoản nào: setup_chart dựng được hệ thống TT99.")
		)
	elif result["verdict"] == "DIFFERENT":
		result["reasons"].append(
			_(
				"Công ty đã có một hệ thống tài khoản khác. ERPCM không thay hệ thống tài khoản đã có; dùng "
				"create_company để tạo một công ty mới với hệ thống TT99."
			)
		)
	return result


@frappe.whitelist(methods=["POST"])
def setup_chart(company=None, names="vi_en"):
	"""Build the TT99 chart on a company that has no account at all; anything else changes nothing.

	It builds the chart only: no warehouses, categories or default accounts (run the two repairs after it).
	"""
	frappe.only_for(ROLES)
	company = _require_company(company, "write")
	_require_names(names)

	result = chart_status(company, names)
	if result["verdict"] != "BUILD":
		return result
	tree = with_names(load_chart()["tree"], names)
	problems = [
		p
		for p in (
			plan.name_length_problem(
				tree, frappe.db.get_value("Company", company, "abbr"), _max_name_length()
			),
			plan.write_limit_problem(frappe.db.count("Account"), _write_limit()),
			_("Công ty đã có bút toán") if result["posted"] else None,
		)
		if p
	]
	if problems:
		result.update(verdict="REFUSE", reasons=problems)
		return result
	_require_clean_transaction()
	try:
		_build(company, tree)
		result.update(verdict="BUILT", accounts=frappe.db.count("Account", {"company": company}), reasons=[])
	except BaseException:
		_forget(company)
		raise
	return result


@frappe.whitelist(methods=["POST"])
def apply_account_categories(company=None):
	"""Repair: create the TT99 Account Categories and assign them to the company's ledger accounts.

	Only when the company's chart is the TT99 one (chart_status MATCH) and nothing is posted. Only this
	company's accounts are touched. A ledger without a category gets its prefix's; a ledger a person gave
	another category keeps it (reported); groups have their category cleared.
	"""
	frappe.only_for(ROLES)
	company = _require_company(company, "write")
	if not _categories_supported():
		return {
			"company": company,
			"verdict": "REFUSE",
			"reasons": [
				_("Account Category của bản ERPNext này thiếu trường root_type; cần ERPNext 16.55 trở lên")
			],
		}
	reasons = plan.may_write(plan.tt99_style(load_chart()["tree"], _rows(company)), _posted(company))
	categories, existing = _categories()
	reasons += category_conflicts(categories, existing)[1]
	if reasons:
		return {"company": company, "verdict": "REFUSE", "reasons": reasons}
	_require_clean_transaction()
	try:
		result = _apply_categories(company, categories, existing)
		changed = result["categories_created"] or result["accounts_changed"]
		result = {"company": company, "verdict": "CHANGED" if changed else "MATCH", **result}
	except BaseException:
		_forget(company)
		raise
	return result


@frappe.whitelist(methods=["POST"])
def set_company_defaults(company=None):
	"""Repair: fill the Company's default-account fields from tt99_company_defaults.json.

	Only when the company's chart is the TT99 one. Nothing posted yet: every default is filled when it is
	empty or does not point at one of the company's ledgers; a field a person set to another ledger is kept
	and reported. Already posting: only the empty Frappe HR fields are filled and this company's Expense
	Claim rows added (the way out after Frappe HR was installed on a site that already had the company);
	no other default changes. The Company is saved through its own validation.
	"""
	frappe.only_for(ROLES)
	company = _require_company(company, "write")
	style = plan.tt99_style(load_chart()["tree"], _rows(company))
	posted = _posted(company)
	reasons = plan.may_write(style, {})
	if posted and not _hrms():
		reasons += plan.may_write(style, posted)[len(reasons) :]
	if reasons:
		return {"company": company, "verdict": "REFUSE", "reasons": reasons}
	_require_clean_transaction()
	try:
		r = _apply_defaults(company, hr_only=bool(posted))
		if r["missing"]:  # nothing was written: the ledgers were checked first
			result = {"company": company, "verdict": "REFUSE", "reasons": r["missing"]}
		else:
			changed = r["set"] or r["expense_claim_types"]
			result = {"company": company, "verdict": "CHANGED" if changed else "MATCH", **r}
			if posted:
				result["scope"] = _(
					"Công ty đã có bút toán: chỉ điền các ô trống của Frappe HR và thêm dòng Expense Claim "
					"của công ty này; không ô mặc định nào khác được đổi."
				)
	except BaseException:
		_forget(company)
		raise
	return result
