"""Bench proof for erpcm's TT99 actions. One step per process, run from <bench>/sites by proof.sh:

    ../env/bin/python proof.py <step> [args]

Importing this file does nothing. Run as a script, it connects only to a site that carries the marker
proof.sh writes when it creates the site (site config `erpcm_proof_site`), and refuses any other.
Every line of evidence starts with "R ". Each expectation prints "R ok" or "R FAIL"; a step with a
failure exits 1, and proof.sh fails the run. Steps that should persist commit, the way `bench execute`
does.
"""

import hashlib
import json
import sys

SITE = "t.local"
MARKER = "erpcm_proof_site"

A = "Cong Ty Thu"  # created by the setup wizard
T = "Cong Ty TT99"  # created by create_company
FAIL = "Cong Ty Loi"  # a create_company forced to fail midway
EMPTY = "Cong Ty Trong"  # a company with no account at all (data import): setup_chart builds on it

frappe = None
s = None
failures = []


def out(*a):
	print("R", *a, flush=True)


def check(condition, label, *detail):
	if condition:
		out("ok  ", label, *detail)
	else:
		failures.append(label)
		out("FAIL", label, *detail)


def account_fields():
	from frappe.model.rename_doc import get_link_fields

	return sorted({f["fieldname"] for f in get_link_fields("Account") if f["parent"] == "Company"})


def snapshot(company):
	rows = frappe.get_all(
		"Account",
		filters={"company": company},
		fields=[
			"name",
			"parent_account",
			"account_type",
			"root_type",
			"is_group",
			"account_number",
			"account_category",
		],
		order_by="name",
	)
	comp = frappe.db.get_value("Company", company, account_fields(), as_dict=True)
	tmpl = sorted(
		frappe.get_all(dt, filters={"company": company}, pluck="name")
		for dt in (
			"Sales Taxes and Charges Template",
			"Purchase Taxes and Charges Template",
			"Item Tax Template",
		)
	)
	blob = json.dumps([rows, comp, tmpl], default=str, sort_keys=True)
	return [len(rows), hashlib.sha256(blob.encode()).hexdigest()[:16]]


def call(fn, *a, **kw):
	"""Run an action the way bench execute does: commit when it returns, roll back when it raises."""
	try:
		r = fn(*a, **kw)
		frappe.db.commit()
		return r
	except Exception as e:
		frappe.db.rollback()
		return {"verdict": f"raised {type(e).__name__}", "reasons": [frappe.utils.strip_html(str(e))[:160]]}


def hrms():
	return "hrms" in frappe.get_installed_apps()


def company_rows(company):
	"""Everything that names the company, for the left-over check."""
	rows = {
		dt: frappe.db.count(dt, {"company": company})
		for dt in ("Account", "Warehouse", "Cost Center", "Department", "Mode of Payment Account")
	}
	if hrms():
		rows["Expense Claim Account"] = frappe.db.count("Expense Claim Account", {"company": company})
	return rows


def other_claim_rows(company):
	if not hrms():
		return []
	return sorted(
		(r.parent, r.company, r.default_account)
		for r in frappe.get_all(
			"Expense Claim Account",
			filters={"company": ("!=", company)},
			fields=["parent", "company", "default_account"],
		)
	)


def step_wizard(args):
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	r = setup_complete(
		{
			"language": "English",
			"country": "Vietnam",
			"timezone": "Asia/Ho_Chi_Minh",
			"currency": "VND",
			"full_name": "Ke Toan Thu",
			"email": "kt@example.com",
			"password": "Thu-mat-khau-1",
			"company_name": A,
			"company_abbr": "CTT",
			"chart_of_accounts": "Standard",
			"fy_start_date": "2026-01-01",
			"fy_end_date": "2026-12-31",
			"domain": "Distribution",
		}
	)
	frappe.db.commit()
	check(
		r.get("status") == "ok",
		"setup wizard",
		A,
		"accounts",
		frappe.db.count("Account", {"company": A}),
		"| apps",
		frappe.get_installed_apps(),
	)


def step_snap(args):
	company, label = args[0], args[1]
	snap = snapshot(company)
	key = f"/tmp/erpcm_snap_{hashlib.md5(company.encode()).hexdigest()}"
	if label == "save":
		open(key, "w").write(json.dumps(snap))
		out("snapshot", company, *snap)
	else:
		check(json.loads(open(key).read()) == snap, f"snapshot {company} {label} equals the first", *snap)


def step_existing(args):
	before = snapshot(A)
	r0 = s.chart_status(A)
	r1, r2, r3 = call(s.setup_chart, A), call(s.apply_account_categories, A), call(s.set_company_defaults, A)
	check(
		r0["verdict"] == "DIFFERENT" and "create_company" in r0["reasons"][0],
		"wizard company: chart_status DIFFERENT",
	)
	check(
		(r1["verdict"], r2["verdict"], r3["verdict"]) == ("DIFFERENT", "REFUSE", "REFUSE"),
		"wizard company: setup_chart DIFFERENT, both repairs refuse",
		r1["verdict"],
		r2["verdict"],
		r3["verdict"],
	)
	check(snapshot(A) == before, "wizard company unchanged")


def step_fail(args):
	kind = args[0]
	categories = frappe.db.count("Account Category")
	erpcm_categories = frappe.db.count("Account Category", {"description": ("like", "%ERPCM%")})
	claim_rows = frappe.db.count("Expense Claim Account") if hrms() else 0

	def failing(company):
		out(
			kind,
			"inside: accounts",
			frappe.db.count("Account", {"company": company}),
			"warehouses",
			frappe.db.count("Warehouse", {"company": company}),
			"ERPCM categories",
			frappe.db.count("Account Category", {"description": ("like", "%ERPCM%")}),
			"- failing now",
		)
		raise KeyboardInterrupt() if kind == "interrupt" else RuntimeError("forced failure after the chart")

	s._apply_defaults = failing
	flag_before = frappe.local.flags.ignore_chart_of_accounts
	try:
		s.create_company(FAIL, "CTL")
		check(False, f"{kind}: create_company raised")
	except BaseException as e:
		check(True, f"{kind}: create_company raised", type(e).__name__)
	check(frappe.local.flags.ignore_chart_of_accounts == flag_before, f"{kind}: chart flag restored")
	frappe.db.commit()  # the worst case: a caller that commits anyway
	open("/tmp/erpcm_fail_counts", "w").write(json.dumps([categories, erpcm_categories, claim_rows]))
	out(kind, "ERPCM categories before the attempt:", erpcm_categories)


def step_left_over(args):
	categories, erpcm_categories, claim_rows = json.loads(open("/tmp/erpcm_fail_counts").read())
	rows = company_rows(FAIL)
	check(not frappe.db.exists("Company", FAIL), "no Company left")
	check(not any(rows.values()), "no row naming the company", rows)
	check(
		frappe.db.count("Account Category") == categories,
		"no Account Category left",
		frappe.db.count("Account Category"),
		"| ERPCM's before",
		erpcm_categories,
	)
	if hrms():
		check(frappe.db.count("Expense Claim Account") == claim_rows, "no Expense Claim row left")
	keys = [k.decode() if isinstance(k, bytes) else k for k in frappe.cache.get_keys(f"*{FAIL}*")]
	keys += [k.decode() if isinstance(k, bytes) else k for k in frappe.cache.get_keys("* - CTL*")]
	check(not keys, "no cache key naming the company", keys)


def step_collation(args):
	"""A category the site already has, spelt differently, is reused; one with another root_type refuses."""
	frappe.get_doc(
		{
			"doctype": "Account Category",
			"account_category_name": "tiền và tương đương tiền",
			"root_type": "Asset",
		}
	).insert()
	frappe.get_doc(
		{"doctype": "Account Category", "account_category_name": "PHẢI TRẢ NGƯỜI BÁN", "root_type": "Asset"}
	).insert()
	frappe.db.commit()
	before = frappe.db.count("Company")
	r = call(s.create_company, T, "TT99")
	check(
		r["verdict"] == "REFUSE" and any("PHẢI TRẢ NGƯỜI BÁN" in x for x in r["reasons"]),
		"a collation-equal category with another root_type refuses",
		r["reasons"],
	)
	check(frappe.db.count("Company") == before, "nothing created")
	frappe.delete_doc("Account Category", "PHẢI TRẢ NGƯỜI BÁN")
	frappe.db.commit()


def step_create_tt99(args):
	others = other_claim_rows(T)
	r = call(s.create_company, T, "TT99")
	want_defaults = 18 if hrms() else 16
	check(r["verdict"] == "CREATED", "create_company", r.get("reasons"))
	check(r.get("accounts") == 189, "189 accounts", r.get("accounts"))
	check(len(r.get("warehouses", [])) == 5, "5 warehouses", r.get("warehouses"))
	check(r.get("cost_center") == "Main - TT99", "cost center", r.get("cost_center"))
	check(
		len(r.get("categories_created", [])) == 37,
		"37 categories created, the existing one reused",
		len(r.get("categories_created", [])),
	)
	cash = frappe.db.get_value("Account", {"company": T, "account_number": "111"}, "account_category")
	check(cash == "tiền và tương đương tiền", "111 gets the category spelt as the site stores it", cash)
	check(
		len(r.get("defaults_set", {})) == want_defaults,
		f"{want_defaults} default accounts",
		len(r.get("defaults_set", {})),
	)
	st = s.chart_status(T)
	check((st["verdict"], st["style"]) == ("MATCH", "vi_en"), "chart_status MATCH vi_en")
	if hrms():
		rows = frappe.get_all("Expense Claim Account", filters={"company": T}, pluck="default_account")
		check(
			rows and all(x.startswith("6428 ") for x in rows),
			"Expense Claim rows for this company on 6428",
			len(rows),
		)
		check(
			other_claim_rows(T) == others,
			"other companies' Expense Claim rows unchanged, row by row",
			len(others),
		)
		hr = frappe.db.get_value(
			"Company", T, ["default_payroll_payable_account", "default_employee_advance_account"]
		)
		check(hr[0].startswith("334 ") and hr[1].startswith("141 "), "HR defaults 334 / 141", hr)
	n = frappe.db.count("Account", {"company": T})
	doc = frappe.get_doc("Company", T)
	doc.phone_no = "0900000000"
	doc.save()
	frappe.db.commit()
	check(
		frappe.db.count("Account", {"company": T}) == n and s.chart_status(T)["verdict"] == "MATCH",
		"saving the Company form afterwards creates no account; still MATCH",
		frappe.db.count("Account", {"company": T}),
	)


def step_refusals(args):
	cases = [
		((T, "XYZ"), "Đã có công ty"),
		((T.upper(), "XYZ"), "Đã có công ty"),
		(("Cong Ty Khac", "TT99"), "Viết tắt"),
		(("Cong Ty Khac", "tt99"), "Viết tắt"),
		(("Cong Ty Dai", "CTTTMDVSXAB"), "142 ký tự"),
		(("Cong Ty Dau", "A B"), "chữ và số"),
		(("Cong Ty Dau", "A%"), "chữ và số"),
		(("Cong Ty Dau", "A-B"), "chữ và số"),
		(("X" * 136, "XY"), "tên công ty quá dài"),
	]
	for (name, abbr), expect in cases:
		before = frappe.db.count("Company")
		r = call(s.create_company, name, abbr)
		check(
			r["verdict"] == "REFUSE"
			and any(expect in x for x in r["reasons"])
			and frappe.db.count("Company") == before,
			f"create_company({name[:20]!r}, {abbr!r}) refused, nothing created",
			r["reasons"][:1],
		)
	r = call(s.create_company, "Cong Ty Dai", "CTTTMDVSXAB", names="vi")
	check(r["verdict"] == "CREATED", "the 11-character abbreviation works with names='vi'")
	frappe.db.set_value("Company", A, "phone_no", "0900000000")
	try:
		s.create_company("Cong Ty Ban", "CTB")
		check(False, "a write already in the transaction refuses")
	except frappe.ValidationError:
		check(True, "a write already in the transaction refuses")
	frappe.db.rollback()
	frappe.db._disable_transaction_control = 1
	try:
		s.create_company("Cong Ty Ban", "CTB")
		check(False, "transaction control off refuses")
	except frappe.ValidationError:
		check(True, "transaction control off refuses")
	finally:
		frappe.db._disable_transaction_control = 0
	frappe.db.rollback()
	check(not frappe.db.exists("Company", "Cong Ty Ban"), "nothing created by either")


def step_limit(args):
	before = frappe.db.count("Company")
	r = call(s.create_company, "Cong Ty Gioi Han", "CGH")
	check(
		r["verdict"] == "REFUSE" and any("max_writes_per_transaction" in x for x in r["reasons"]),
		"max_writes_per_transaction 1500: refused",
		frappe.conf.get("max_writes_per_transaction"),
	)
	check(
		frappe.db.count("Company") == before and not frappe.db.exists("Company", "Cong Ty Gioi Han"),
		"nothing created",
	)


def step_setup_of(args):
	"""The non-chart setup of the wizard company and of the TT99 company, side by side."""

	def setup(company):
		abbr = frappe.db.get_value("Company", company, "abbr")

		def strip(v):
			return v.replace(f" - {abbr}", " - ABBR").replace(company, "COMPANY") if isinstance(v, str) else v

		meta = frappe.get_meta("Company")
		skip = set(account_fields()) | {
			"name",
			"company_name",
			"abbr",
			"creation",
			"modified",
			"modified_by",
			"owner",
			"lft",
			"rgt",
			"idx",
			"company_description",
			"transactions_annual_history",
			"sales_monthly_history",
			"phone_no",
		}
		comp = frappe.db.get_value("Company", company, "*", as_dict=True)
		return {
			"company fields": {
				f.fieldname: strip(comp.get(f.fieldname))
				for f in meta.fields
				if f.fieldname in comp and f.fieldname not in skip
			},
			"warehouses": sorted(
				(strip(w.name), w.is_group, w.warehouse_type, strip(w.parent_warehouse), w.account)
				for w in frappe.get_all(
					"Warehouse",
					filters={"company": company},
					fields=["name", "is_group", "warehouse_type", "parent_warehouse", "account"],
				)
			),
			"cost centers": sorted(
				(strip(c.name), c.is_group, strip(c.parent_cost_center))
				for c in frappe.get_all(
					"Cost Center",
					filters={"company": company},
					fields=["name", "is_group", "parent_cost_center"],
				)
			),
			"departments": sorted(
				strip(d) for d in frappe.get_all("Department", filters={"company": company}, pluck="name")
			),
			"mode of payment rows": sorted(
				frappe.get_all("Mode of Payment Account", filters={"company": company}, pluck="parent")
			),
			"expense claim rows": sorted(
				frappe.get_all("Expense Claim Account", filters={"company": company}, pluck="parent")
			)
			if hrms()
			else [],
			"tax templates": sorted(
				strip(t)
				for dt in (
					"Sales Taxes and Charges Template",
					"Purchase Taxes and Charges Template",
					"Item Tax Template",
				)
				for t in frappe.get_all(dt, filters={"company": company}, pluck="name")
			),
			"account fields set": sorted(f for f in account_fields() if comp.get(f)),
		}

	wizard, tt99 = setup(A), setup(T)
	diffs = {
		f: (v, tt99["company fields"].get(f))
		for f, v in wizard["company fields"].items()
		if v != tt99["company fields"].get(f)
	}
	out(
		"company fields (not accounts) that differ, wizard vs TT99:",
		json.dumps(diffs, ensure_ascii=False, default=str),
	)
	check(set(diffs) <= {"domain"}, "no Company field differs but domain")
	for key in ("warehouses", "cost centers", "departments", "mode of payment rows", "expense claim rows"):
		check(
			wizard[key] == tt99[key],
			f"{key}: same",
			json.dumps(wizard[key], ensure_ascii=False, default=str)[:150],
		)
	check(
		wizard["tax templates"] == ["Vietnam Tax - ABBR"] * 3 and tt99["tax templates"] == [],
		"tax templates: the wizard's three 'Vietnam Tax', none on the TT99 company",
	)
	only_w = sorted(set(wizard["account fields set"]) - set(tt99["account fields set"]))
	only_t = sorted(set(tt99["account fields set"]) - set(wizard["account fields set"]))
	out("Company account fields set by the wizard only:", only_w, "| by ERPCM only:", only_t)
	check(not only_w, "every account field the wizard sets is set", len(tt99["account fields set"]))


def step_sitewide(args):
	"""What one create_company writes outside the new company (docs: what create_company changes)."""
	stamp = frappe.utils.now()
	frappe.db.sql("select sleep(1)")
	ps = set(frappe.get_all("Property Setter", pluck="name"))
	r = call(s.create_company, "Cong Ty Dau Vet", "CDV")
	check(r["verdict"] == "CREATED", "create_company 'Cong Ty Dau Vet'")
	changed = {}
	doctypes = [
		"Currency",
		"Mode of Payment",
		"Financial Report Template",
		"Account Category",
		"Property Setter",
		"Global Defaults",
		"Stock Settings",
		"Accounts Settings",
	]
	if hrms():
		doctypes.append("Expense Claim Type")
	for dt in doctypes:
		names = (
			frappe.get_all(dt, filters={"modified": (">", stamp)}, pluck="name")
			if not frappe.get_meta(dt).issingle
			else ([dt] if str(frappe.db.get_single_value(dt, "modified") or "") > stamp else [])
		)
		if names:
			changed[dt] = sorted(names)
	want = {
		"Currency": ["VND"],
		"Mode of Payment": ["Cash"],
		"Property Setter": ["Purchase Receipt-provisional_expense_account-hidden"],
	}
	if hrms():
		want["Expense Claim Type"] = sorted(frappe.get_all("Expense Claim Type", pluck="name"))
	check(
		changed == want,
		"outside the new company, exactly the documented rows change",
		json.dumps(changed, ensure_ascii=False),
	)
	check(set(frappe.get_all("Property Setter", pluck="name")) == ps, "no Property Setter is added")


def step_empty(args):
	if not frappe.db.exists("Company", EMPTY):
		frappe.local.flags.ignore_chart_of_accounts = True
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": EMPTY,
				"abbr": "CTR",
				"default_currency": "VND",
				"country": "Vietnam",
			}
		).insert()
		frappe.local.flags.ignore_chart_of_accounts = False
		frappe.db.commit()
	check(s.chart_status(EMPTY)["verdict"] == "BUILD", "a company with no account: BUILD")
	check(call(s.setup_chart, EMPTY)["verdict"] == "BUILT", "setup_chart builds")
	check(frappe.db.count("Account", {"company": EMPTY}) == 189, "189 accounts")
	check(call(s.apply_account_categories, EMPTY)["verdict"] == "CHANGED", "categories applied")
	check(call(s.set_company_defaults, EMPTY)["verdict"] == "CHANGED", "defaults set")
	again = [
		call(f, EMPTY)["verdict"] for f in (s.setup_chart, s.apply_account_categories, s.set_company_defaults)
	]
	check(again == ["MATCH"] * 3, "second runs MATCH", again)
	out(
		"warehouses on that company (setup_chart creates none):",
		frappe.db.count("Warehouse", {"company": EMPTY}),
	)


def step_http(args):
	from frappe.app import application
	from werkzeug.test import Client

	frappe.destroy()
	headers = {"Host": SITE}
	c = Client(application)
	c.post("/api/method/login", data={"usr": "Administrator", "pwd": "admin"}, headers=headers)

	def status(r):
		body = json.loads(r.get_data(as_text=True) or "{}")
		msg = body.get("message")
		return r.status_code, msg.get("verdict") if isinstance(msg, dict) else body.get("exc_type")

	base = "/api/method/erpcm.vn.accounting.setup."
	check(
		status(c.get(base + "chart_status", query_string={"company": T}, headers=headers)) == (200, "MATCH"),
		"GET chart_status 200",
	)
	check(
		status(c.get(base + "chart_status", query_string={"company": "Khong Co"}, headers=headers))[0] == 403,
		"GET chart_status of an unknown company 403",
	)
	for method in ("create_company", "setup_chart", "apply_account_categories", "set_company_defaults"):
		check(
			status(c.get(base + method, query_string={"company": T}, headers=headers))[0] == 403,
			f"GET {method} 403",
		)
	check(
		status(
			c.post(
				base + "create_company",
				data={"company_name": "Cong Ty Qua Web", "abbr": "CTW", "country": "Italy"},
				headers=headers,
			)
		)
		== (200, "CREATED"),
		"POST create_company 200 (a country argument is ignored)",
	)
	frappe.init(site=SITE, sites_path=".")
	frappe.connect()
	check(
		frappe.db.get_value("Company", "Cong Ty Qua Web", "country") == "Vietnam", "the company is Vietnamese"
	)


def step_post(args):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

	wh = frappe.db.get_value("Company", T, "default_warehouse")
	if not frappe.db.exists("Item", "HANG-THU"):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "HANG-THU",
				"item_name": "Hang thu",
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert()
	for dt, field, name in (
		("Customer", "customer_name", "Khach Thu"),
		("Supplier", "supplier_name", "NCC Thu"),
	):
		if not frappe.db.exists(dt, name):
			frappe.get_doc({"doctype": dt, field: name}).insert()
	day = "2026-06-15"
	docs = []
	pr = frappe.get_doc(
		{
			"doctype": "Purchase Receipt",
			"company": T,
			"supplier": "NCC Thu",
			"posting_date": day,
			"set_posting_time": 1,
			"items": [{"item_code": "HANG-THU", "qty": 10, "rate": 100000, "warehouse": wh}],
		}
	).insert()
	pr.submit()
	docs.append(pr)
	pi = make_purchase_invoice(pr.name)
	pi.update({"posting_date": day, "set_posting_time": 1, "bill_no": "HD-THU-1"})
	pi.insert()
	pi.submit()
	docs.append(pi)
	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": T,
			"customer": "Khach Thu",
			"posting_date": day,
			"set_posting_time": 1,
			"due_date": day,
			"items": [{"item_code": "HANG-THU", "qty": 2, "rate": 150000}],
		}
	).insert()
	si.submit()
	docs.append(si)
	pe = get_payment_entry("Sales Invoice", si.name)
	pe.update({"posting_date": day, "reference_no": "PT-THU-1", "reference_date": day})
	pe.insert()
	pe.submit()
	docs.append(pe)
	for purpose, field in (("Material Receipt", "t_warehouse"), ("Material Issue", "s_warehouse")):
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"company": T,
				"stock_entry_type": purpose,
				"posting_date": day,
				"set_posting_time": 1,
				"items": [{"item_code": "HANG-THU", "qty": 1, "basic_rate": 100000, field: wh}],
			}
		).insert()
		se.submit()
		docs.append(se)
	# ERPNext 16.55 posts a Sales Invoice's own write_off_amount only on POS invoices; outside POS a small
	# difference is written off as a Payment Entry deduction to the company's write_off_account.
	wo = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": T,
			"customer": "Khach Thu",
			"posting_date": day,
			"set_posting_time": 1,
			"due_date": day,
			"items": [{"item_code": "HANG-THU", "qty": 1, "rate": 150000}],
		}
	).insert()
	wo.submit()
	docs.append(wo)
	pw = get_payment_entry("Sales Invoice", wo.name)
	pw.update(
		{
			"posting_date": day,
			"reference_no": "PT-THU-2",
			"reference_date": day,
			"paid_amount": 140000,
			"received_amount": 140000,
		}
	)
	pw.append(
		"deductions",
		{
			"account": frappe.db.get_value("Company", T, "write_off_account"),
			"cost_center": frappe.db.get_value("Company", T, "cost_center"),
			"amount": 10000,
		},
	)
	pw.insert()
	pw.submit()
	docs.append(pw)
	frappe.db.commit()
	for d in docs:
		gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": d.name, "is_cancelled": 0},
			fields=["account", "debit", "credit"],
		)
		check(
			frappe.db.get_value(d.doctype, d.name, "docstatus") == 1 and gl,
			f"{d.doctype} {d.get('purpose') or ''} submits",
			[(g.account.split(" - ")[0], g.debit, g.credit) for g in gl],
		)
	check(
		any(
			g.account.startswith("811 ")
			for g in frappe.get_all("GL Entry", filters={"voucher_no": pw.name}, fields=["account"])
		),
		"the write-off goes to 811 (write_off_account)",
	)


def step_sce(args):
	sce = frappe.get_doc(
		{"doctype": "Stock Closing Entry", "company": T, "from_date": "2026-01-01", "to_date": "2026-06-30"}
	).insert()
	sce.submit()
	frappe.db.commit()
	out("stock closing entry", sce.name, frappe.db.get_value("Stock Closing Entry", sce.name, "status"))


def step_pcv(args):
	check(
		frappe.db.get_value("Stock Closing Entry", {"company": T}, "status") == "Completed",
		"stock closing entry completed",
	)
	closing = frappe.get_all("Account", filters={"company": T, "account_number": "911"}, pluck="name")[0]
	pcv = frappe.get_doc(
		{
			"doctype": "Period Closing Voucher",
			"company": T,
			"transaction_date": "2026-06-30",
			"fiscal_year": "2026",
			"period_start_date": "2026-01-01",
			"period_end_date": "2026-06-30",
			"closing_account_head": closing,
			"remarks": "Khoa so thu",
		}
	).insert()
	pcv.submit()
	frappe.db.commit()
	pl = frappe.db.sql(
		"""select sum(debit - credit) from `tabGL Entry` g join tabAccount a on a.name = g.account
		where g.company = %s and a.report_type = 'Profit and Loss' and g.is_cancelled = 0""",
		T,
	)[0][0]
	b911 = frappe.db.sql(
		"""select sum(debit - credit) from `tabGL Entry` g join tabAccount a on a.name = g.account
		where g.company = %s and a.account_number = '911' and g.is_cancelled = 0""",
		T,
	)[0][0]
	check(
		frappe.db.get_value("Period Closing Voucher", pcv.name, "gle_processing_status") == "Completed"
		and pl == 0,
		"period closing voucher: P&L to 0 through 911",
	)
	check(b911 == -440000, "440,000 left on 911 until it is moved to 4212", b911)


def step_after_post(args):
	before = snapshot(T)
	r = [
		call(f, T)["verdict"]
		for f in (s.chart_status, s.setup_chart, s.apply_account_categories, s.set_company_defaults)
	]
	# With Frappe HR, set_company_defaults may still fill the HR part of a posting company;
	# here it is complete.
	want = ["MATCH", "MATCH", "REFUSE", "MATCH" if hrms() else "REFUSE"]
	check(
		r == want and snapshot(T) == before,
		"after posting: chart_status / setup_chart MATCH, categories refused,"
		" defaults refused or nothing to do",
		r,
	)


def step_roles(args):
	for email, roles in (
		("ke-toan-vien@example.com", ["Accounts User"]),
		("ke-toan-truong@example.com", ["Accounts Manager"]),
	):
		if not frappe.db.exists("User", email):
			u = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
				}
			)
			u.insert()
			u.add_roles(*roles)
	frappe.db.commit()
	for email, allowed in (("ke-toan-vien@example.com", False), ("ke-toan-truong@example.com", True)):
		frappe.set_user(email)
		seen = []
		for fn, args_ in (
			(s.chart_status, (T,)),
			(s.setup_chart, (T,)),
			(s.apply_account_categories, (T,)),
			(s.set_company_defaults, (T,)),
			(s.create_company, ("Cong Ty Vai Tro " + email[:3], "CVT" + email[:1].upper())),
		):
			try:
				seen.append(fn(*args_)["verdict"])
			except frappe.PermissionError:
				seen.append("403")
			frappe.db.rollback()
		check(("403" not in seen) if allowed else (seen == ["403"] * 5), f"as {email}", seen)
	frappe.set_user("Administrator")


def step_create(args):
	name, abbr = args[0], args[1]
	names = args[2] if len(args) > 2 else "vi_en"
	if len(args) > 3:
		out(
			"innodb_snapshot_isolation in this session:",
			frappe.db.sql("select @@innodb_snapshot_isolation")[0][0],
		)
	r = call(s.create_company, name, abbr, names=names)
	st = s.chart_status(name) if r["verdict"] == "CREATED" else {}
	check(
		r["verdict"] == "CREATED" and st.get("verdict") == "MATCH" and st.get("style") == names,
		f"create_company({name!r}, names={names!r}) -> MATCH {names}",
		r.get("accounts"),
	)


def step_hr(args):
	"""Frappe HR on the TT99 company: an Employee Advance gets paid; Payroll Entry's account check passes."""
	from hrms.overrides.employee_payment_entry import get_payment_entry_for_employee

	emp = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Nhan Vien",
			"company": T,
			"gender": "Male",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2026-01-01",
			"status": "Active",
		}
	).insert()
	ea = frappe.get_doc(
		{
			"doctype": "Employee Advance",
			"employee": emp.name,
			"company": T,
			"posting_date": "2026-06-15",
			"advance_amount": 1000000,
			"exchange_rate": 1,
			"purpose": "thu",
			"advance_account": frappe.db.get_value("Company", T, "default_employee_advance_account"),
		}
	).insert()
	ea.submit()
	pe = get_payment_entry_for_employee("Employee Advance", ea.name)
	pe.update({"reference_no": "TU-1", "reference_date": "2026-06-15", "posting_date": "2026-06-15"})
	pe.insert()
	pe.submit()
	frappe.db.commit()
	check(
		frappe.db.get_value("Employee Advance", ea.name, "status") == "Paid",
		"Employee Advance on 141 paid",
		ea.advance_account,
	)
	payroll = frappe.get_doc(
		{
			"doctype": "Payroll Entry",
			"company": T,
			"posting_date": "2026-06-30",
			"payroll_frequency": "Monthly",
			"start_date": "2026-06-01",
			"end_date": "2026-06-30",
			"currency": "VND",
			"exchange_rate": 1,
			"cost_center": frappe.db.get_value("Company", T, "cost_center"),
			"payroll_payable_account": frappe.db.get_value("Company", T, "default_payroll_payable_account"),
			"payment_account": frappe.db.get_value("Company", T, "default_cash_account"),
		}
	).insert()
	try:
		payroll.validate_payroll_payable_account()  # what Payroll Entry checks before submit
		check(True, "Payroll Entry's payable-account check passes on 334", payroll.payroll_payable_account)
	except frappe.ValidationError as e:
		check(False, "Payroll Entry's payable-account check passes on 334", str(e)[:100])
	frappe.db.rollback()


def step_hr_after(args):
	"""Frappe HR installed after the companies.

	Save first and HR creates an account; repair first and it does not.
	"""
	saved_first = "Cong Ty Ten Viet"
	n = frappe.db.count("Account", {"company": saved_first})
	frappe.get_doc("Company", saved_first).save()
	frappe.db.commit()
	check(
		frappe.db.count("Account", {"company": saved_first}) == n + 1
		and s.chart_status(saved_first)["verdict"] == "DIFFERENT",
		"saving the Company form before set_company_defaults: Frappe HR adds 'Expense Claims' (documented)",
	)
	r = call(s.set_company_defaults, T)
	check(
		r["verdict"] == "CHANGED"
		and set(r["set"]) == {"default_payroll_payable_account", "default_employee_advance_account"}
		and r.get("scope"),
		"set_company_defaults on the posted TT99 company fills " "only the Frappe HR fields and claim rows",
		r.get("set"),
		len(r.get("expense_claim_types", [])),
	)
	n = frappe.db.count("Account", {"company": T})
	frappe.get_doc("Company", T).save()
	frappe.db.commit()
	check(
		frappe.db.count("Account", {"company": T}) == n and s.chart_status(T)["verdict"] == "MATCH",
		"after it, saving the Company form adds no account; still MATCH",
	)


STEPS = {name[5:].replace("_", "-"): fn for name, fn in globals().items() if name.startswith("step_")}


def main():
	global frappe, s
	import frappe as _frappe

	frappe = _frappe
	frappe.init(site=SITE, sites_path=".")
	if not frappe.conf.get(MARKER):
		print(
			f"refusing: site {SITE} has no {MARKER} in its site config; proof.py runs only on the bench proof.sh built"
		)
		return 2
	frappe.connect()
	frappe.set_user("Administrator")
	try:
		from erpcm.vn.accounting import setup

		s = setup
	except ImportError:  # before install-app: only the wizard and snapshot steps run
		s = None
	STEPS[sys.argv[1]](sys.argv[2:])
	return 1 if failures else 0


if __name__ == "__main__":
	sys.exit(main())
