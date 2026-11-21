"""A small in-memory Frappe for testing setup.py without a site.

It models what setup.py's promises rest on, and nothing more: a transaction whose rollback restores every
table and whose write counter grows with each write; names compared the way MariaDB's utf8mb4_unicode_ci
compares them (case, accents and trailing spaces ignored; "đ" is not "d");
frappe.local.flags.ignore_chart_of_accounts suppressing ERPNext's default chart on Company insert; Frappe
HR's doctypes existing only when "hrms" is installed; and then Frappe HR's Company.on_update creating an
"Expense Claims" account for every Expense Claim Type without a row for the company. What it does not model —
real SQL, nested sets, ERPNext's validations — rests on the bench proof.
"""

import copy
import sys
import types
import unicodedata

from erpcm.vn.accounting import chart, plan


class ValidationError(Exception):
	pass


class PermissionError_(Exception):
	pass


class DoesNotExistError(ValidationError):
	pass


def norm(value):
	if not isinstance(value, str):
		return value
	text = unicodedata.normalize("NFKD", value.rstrip()).casefold()
	return "".join(c for c in text if not unicodedata.combining(c))  # "đ" stays "đ", as in MariaDB 11.8


def matches(row, filters):
	for field, want in (filters or {}).items():
		have = row.get(field)
		if isinstance(want, tuple):
			op, arg = want
			if op == "in" and norm(have) not in {norm(a) for a in arg}:
				return False
			if op == "!=" and norm(have) == norm(arg):
				return False
			if op == "like" and norm(arg.strip("%")) not in norm(have or ""):
				return False
		elif norm(have) != norm(want):
			return False
	return True


class Site:
	"""Tables of dict rows keyed by name, plus the knobs a test turns."""

	def __init__(self):
		self.tables = {
			dt: {}
			for dt in (
				"Company",
				"Account",
				"Account Category",
				"Warehouse",
				"Mode of Payment Account",
				"Expense Claim Type",
				"Expense Claim Account",
				"GL Entry",
				"Stock Ledger Entry",
				"Payment Ledger Entry",
			)
		}
		self.apps = ["frappe", "erpnext", "erpcm"]
		self.flag_ignored = False  # ERPNext builds its chart even with the flag (the check after insert)
		self.drop_account = None  # create_charts silently skips this account name (the check after the build)
		self.fail_in_build = False  # create_charts raises halfway, the way a database error would
		self.missing_fields = set()  # (doctype, fieldname) this ERPNext lacks
		self.cleared = []

	def find(self, doctype, name):
		for key in self.tables[doctype]:
			if norm(key) == norm(name):
				return key
		return None

	def rows(self, doctype, filters=None):
		if doctype.startswith("Expense Claim") and "hrms" not in self.apps:
			raise DoesNotExistError(f"DocType {doctype} not found")
		if isinstance(filters, str):
			key = self.find(doctype, filters)
			return [self.tables[doctype][key]] if key else []
		return [r for r in self.tables[doctype].values() if matches(r, filters)]


class FakeDB:
	MAX_WRITES_PER_TRANSACTION = 200_000

	def __init__(self, site):
		self.site = site
		self.transaction_writes = 0
		self._disable_transaction_control = 0
		self.auto_commit_on_many_writes = 0
		self.lookups = []
		self.commit()

	def commit(self):
		self.snapshot = copy.deepcopy(self.site.tables)
		self.transaction_writes = 0

	def rollback(self):
		self.site.tables = copy.deepcopy(self.snapshot)
		self.transaction_writes = 0

	def write(self, doctype, row):
		self.site.tables[doctype][row["name"]] = row
		self.transaction_writes += 1

	def exists(self, doctype, filters):
		self.lookups.append((doctype, filters))
		return bool(self.site.rows(doctype, filters))

	def get_value(self, doctype, name, fields, as_dict=False):
		self.lookups.append((doctype, name))
		rows = self.site.rows(doctype, name)
		if not rows:
			return None
		row = rows[0]
		if isinstance(fields, str):
			return row.get(fields)
		values = types.SimpleNamespace(**{f: row.get(f) for f in fields})
		return values if as_dict else tuple(row.get(f) for f in fields)

	def count(self, doctype, filters=None):
		return len(self.site.rows(doctype, filters))

	def set_value(self, doctype, name, field, value, update_modified=True):
		self.site.tables[doctype][name][field] = value
		self.transaction_writes += 1

	def sql(self, query, *args, **kwargs):
		if "information_schema" in query:
			return [(140,)]
		return []


def install(monkeypatch):
	"""Install the fake as `frappe` (and the two ERPNext imports setup.py makes); return (frappe, site)."""
	site = Site()
	frappe = types.ModuleType("frappe")
	frappe.ValidationError = ValidationError
	frappe.PermissionError = PermissionError_
	frappe.DoesNotExistError = DoesNotExistError
	frappe.db = FakeDB(site)
	frappe.conf = {}
	frappe.local = types.SimpleNamespace(
		flags=types.SimpleNamespace(ignore_chart_of_accounts=None, ignore_update_nsm=False)
	)
	frappe.flags = types.SimpleNamespace(in_import=False)
	frappe.denied = set()

	def throw(message, exc=ValidationError):
		raise exc(message)

	def has_permission(doctype, ptype=None, doc=None, throw=False):
		allowed = ptype not in frappe.denied
		if not allowed and throw:
			raise PermissionError_(f"no {ptype} on {doctype}")
		return allowed

	frappe.throw = throw
	frappe._ = lambda text: text
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.only_for = lambda roles: None
	frappe.has_permission = has_permission
	frappe.get_installed_apps = lambda: list(site.apps)
	frappe.clear_document_cache = lambda doctype, name=None: site.cleared.append((doctype, name))
	frappe.clear_cache = lambda: site.cleared.append(("*", None))

	def has_field(doctype, field):
		if (doctype, field) in site.missing_fields:
			return False
		return (
			doctype != "Company"
			or not field.startswith(("default_payroll", "default_employee"))
			or "hrms" in site.apps
		)

	frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda f: has_field(doctype, f))

	def get_all(doctype, filters=None, fields=None, order_by=None, pluck=None, as_list=False):
		rows = site.rows(doctype, filters)
		if pluck:
			return [r[pluck] for r in rows]
		if as_list:
			return [tuple(r.get(f) for f in fields) for r in rows]
		return [types.SimpleNamespace(**r) if not isinstance(r, dict) else _Row(r) for r in rows]

	frappe.get_all = get_all

	def get_doc(arg, name=None):
		if isinstance(arg, dict):
			return NewDoc(frappe, site, arg)
		if arg == "Company":
			return CompanyDoc(frappe, site, site.find("Company", name))
		if arg == "Expense Claim Type":
			return ClaimTypeDoc(frappe, site, name)
		raise KeyError(arg)

	frappe.get_doc = get_doc

	def create_charts(company, custom_chart=None):
		abbr = site.tables["Company"][company]["abbr"]
		frappe.local.flags.ignore_update_nsm = True  # as ERPNext does; reset only at the end
		for i, (parent, name, node, root_type) in enumerate(chart.iter_nodes(custom_chart)):
			if site.fail_in_build and i == 50:
				raise RuntimeError("database error halfway through create_charts")
			number = node.get("account_number") or ""
			docname = plan.docname(number, name, abbr)
			if docname == site.drop_account:
				continue
			parent_docname = None
			if parent is not None:
				parent_docname = next(
					r["name"]
					for r in site.tables["Account"].values()
					if r["company"] == company and r["account_name"] == parent
				)
			frappe.db.write(
				"Account",
				{
					"name": docname,
					"company": company,
					"account_name": name,
					"account_number": number,
					"parent_account": parent_docname,
					"account_type": node.get("account_type"),
					"root_type": root_type,
					"is_group": chart.is_group(node),
					"account_category": None,
				},
			)
		frappe.db.auto_commit_on_many_writes = 1  # rebuild_tree leaves it on
		frappe.local.flags.ignore_update_nsm = False

	def sync_financial_report_templates():
		frappe.flags.in_import = True  # as ERPNext does; it resets it only when nothing fails

	modules = {"frappe": frappe}
	for name in ("frappe.utils",):
		modules[name] = types.ModuleType(name)
	modules["frappe.utils"].cint = lambda v: int(v or 0)
	frappe.utils = modules["frappe.utils"]
	for path, attrs in (
		(
			"erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts",
			{"create_charts": create_charts},
		),
		(
			"erpnext.accounts.doctype.financial_report_template.financial_report_template",
			{"sync_financial_report_templates": sync_financial_report_templates},
		),
	):
		parts = path.split(".")
		for i in range(1, len(parts) + 1):
			modules.setdefault(".".join(parts[:i]), types.ModuleType(".".join(parts[:i])))
		for k, v in attrs.items():
			setattr(modules[path], k, v)
	for name, module in modules.items():
		monkeypatch.setitem(sys.modules, name, module)
	monkeypatch.delitem(sys.modules, "erpcm.vn.accounting.setup", raising=False)
	return frappe, site


class _Row(dict):
	__getattr__ = dict.get


class NewDoc:
	def __init__(self, frappe, site, data):
		self.frappe, self.site, self.data = frappe, site, dict(data)

	def insert(self, ignore_permissions=False):
		doctype = self.data.pop("doctype")
		if doctype == "Company":
			name = self.data["company_name"]
			self.data.update(name=name, cost_center=f"Main - {self.data['abbr']}")
			self.frappe.db.write("Company", self.data)
			if not self.frappe.local.flags.ignore_chart_of_accounts or self.site.flag_ignored:
				self.frappe.db.write(
					"Account",
					{
						"name": f"Application of Funds (Assets) - {self.data['abbr']}",
						"company": name,
						"account_name": "Application of Funds (Assets)",
						"is_group": 1,
						"root_type": "Asset",
					},
				)
			return CompanyDoc(self.frappe, self.site, name)
		if doctype == "Account Category":
			self.data["name"] = self.data["account_category_name"]
		self.frappe.db.write(doctype, self.data)
		return self


class CompanyDoc:
	def __init__(self, frappe, site, name):
		self.frappe, self.site, self.name = frappe, site, name

	def get(self, field):
		return self.site.tables["Company"][self.name].get(field)

	@property
	def default_cash_account(self):
		return self.get("default_cash_account")

	def update(self, changes):
		self.site.tables["Company"][self.name].update(changes)

	def reload(self):
		pass

	def save(self):
		self.frappe.db.transaction_writes += 1
		if "hrms" in self.site.apps and not self.frappe.local.flags.ignore_chart_of_accounts:
			# Frappe HR's set_expense_claim_type_accounts
			for claim_type in self.site.tables["Expense Claim Type"]:
				if not self.site.rows("Expense Claim Account", {"parent": claim_type, "company": self.name}):
					abbr = self.get("abbr")
					self.frappe.db.write(
						"Account",
						{
							"name": f"Expense Claims - {abbr}",
							"company": self.name,
							"account_name": "Expense Claims",
							"parent_account": None,
							"is_group": 0,
							"root_type": "Expense",
						},
					)

	def create_default_warehouses(self):
		abbr = self.get("abbr")
		for w in ("All Warehouses", "Stores", "Work In Progress", "Finished Goods", "Goods In Transit"):
			self.frappe.db.write("Warehouse", {"name": f"{w} - {abbr}", "company": self.name})

	def set_mode_of_payment_account(self):
		self.frappe.db.write(
			"Mode of Payment Account",
			{
				"name": f"Cash {self.name}",
				"parent": "Cash",
				"company": self.name,
				"default_account": self.get("default_cash_account"),
			},
		)


class ClaimTypeDoc:
	"""An Expense Claim Type with its child rows loaded; save() writes the rows back as they now are."""

	def __init__(self, frappe, site, name):
		self.frappe, self.site, self.name = frappe, site, name
		self.accounts = [dict(r) for r in site.rows("Expense Claim Account", {"parent": name})]

	def append(self, field, row):
		getattr(self, field).append(dict(row, parent=self.name))

	def save(self, ignore_permissions=False):
		table = self.site.tables["Expense Claim Account"]
		for key in [k for k, r in table.items() if r["parent"] == self.name]:
			del table[key]
		for i, row in enumerate(self.accounts):
			name = row.get("name") or f"{self.name}-{i}-{row['company']}"
			self.frappe.db.write("Expense Claim Account", dict(row, name=name))
