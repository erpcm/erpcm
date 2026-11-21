"""Static checks on the accounting code, read as source (AST). Nothing is imported, so no frappe is needed.

What these cannot check — that ERPNext's chart flag holds, that a failure leaves nothing behind, that the
created company works — rests on the bench proof in tools/bench (docs/ROADMAP.md).
"""

import ast
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNTING = os.path.join(REPO, "erpcm", "vn", "accounting")

PURE = ("chart.py", "categories.py", "plan.py")
WRITERS = {"create_company", "setup_chart", "apply_account_categories", "set_company_defaults"}
ON_A_COMPANY = {"chart_status", "setup_chart", "apply_account_categories", "set_company_defaults"}


def parse(path):
	with open(path, encoding="utf-8") as f:
		return ast.parse(f.read(), filename=path)


def imported_roots(tree):
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			yield from (a.name.split(".")[0] for a in node.names)
		elif isinstance(node, ast.ImportFrom) and node.module:
			yield node.module.split(".")[0]


def test_pure_modules_do_not_import_frappe():
	for name in PURE:
		roots = set(imported_roots(parse(os.path.join(ACCOUNTING, name))))
		assert not roots & {"frappe", "erpnext"}, (name, roots)


def whitelist_decorator(fn):
	for d in fn.decorator_list:
		target = d.func if isinstance(d, ast.Call) else d
		if isinstance(target, ast.Attribute) and target.attr == "whitelist":
			return d
	return None


def setup_functions():
	tree = parse(os.path.join(ACCOUNTING, "setup.py"))
	return tree, {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef) and whitelist_decorator(n)}


def body_without_docstring(fn):
	body = fn.body
	if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
		body = body[1:]
	return body


def call_of(stmt):
	"""The called name of a statement that is a call, or an assignment of one ('frappe.only_for', ...)."""
	value = stmt.value if isinstance(stmt, (ast.Expr, ast.Assign)) else None
	if not isinstance(value, ast.Call):
		return None
	func = value.func
	if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
		return f"{func.value.id}.{func.attr}"
	return getattr(func, "id", None)


def test_the_whitelisted_functions():
	_, fns = setup_functions()
	assert set(fns) == WRITERS | {"chart_status"}


def test_every_action_checks_the_role_first_then_the_company_and_its_permission():
	tree, fns = setup_functions()
	for name, fn in fns.items():
		body = body_without_docstring(fn)
		assert call_of(body[0]) == "frappe.only_for", name
		if name in ON_A_COMPANY:
			second = body[1]
			assert isinstance(second, ast.Assign) and second.targets[0].id == "company", name
			assert call_of(second) == "_require_company", name
			assert second.value.args[1].value == ("read" if name == "chart_status" else "write"), name
		else:
			assert call_of(body[1]) == "frappe.has_permission", name
			assert [a.value for a in body[1].value.args] == ["Company", "create"], name
			assert any(k.arg == "throw" and k.value.value is True for k in body[1].value.keywords), name
	roles = next(
		n.value
		for n in tree.body
		if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "ROLES"
	)
	assert {e.value for e in roles.elts} == {"System Manager", "Accounts Manager"}

	require = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_require_company")
	calls = {call_of(s) for s in ast.walk(require) if isinstance(s, (ast.Expr, ast.Assign))}
	source = ast.unparse(require)
	assert "frappe.has_permission('Company', ptype, name)" in source
	assert "frappe.PermissionError" in source, "an unknown company and a forbidden one give the same 403"
	assert "frappe.db.get_value" in source and calls


def test_every_whitelisted_function_can_be_called_without_arguments():
	_, fns = setup_functions()
	for name, fn in fns.items():
		assert len(fn.args.defaults) == len(fn.args.args), f"{name}: a missing argument must be a clean error"


def test_writing_actions_are_post_only_and_none_allows_guests():
	_, fns = setup_functions()
	for name, fn in fns.items():
		d = whitelist_decorator(fn)
		kwargs = {k.arg: k.value for k in d.keywords} if isinstance(d, ast.Call) else {}
		assert "allow_guest" not in kwargs or kwargs["allow_guest"].value is False, name
		if name in WRITERS:
			methods = kwargs.get("methods")
			assert isinstance(methods, ast.List), name
			assert [e.value for e in methods.elts] == ["POST"], name


def test_writing_actions_refuse_a_dirty_transaction_and_undo_on_any_failure():
	_, fns = setup_functions()
	for name in WRITERS:
		fn = fns[name]
		calls = [call_of(s) for s in ast.walk(fn) if isinstance(s, (ast.Expr, ast.Assign))]
		assert "_require_clean_transaction" in calls, name
		tries = [t for t in ast.walk(fn) if isinstance(t, ast.Try)]
		assert tries, name
		for t in tries:
			for handler in t.handlers:
				assert getattr(handler.type, "id", None) == "BaseException", f"{name}: Ctrl-C must undo too"
				assert "_forget" in ast.unparse(handler), name
				assert any(isinstance(s, ast.Raise) for s in handler.body), name


def test_forget_clears_caches_before_the_rollback_and_survives_a_lost_connection():
	tree = parse(os.path.join(ACCOUNTING, "setup.py"))
	forget = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_forget")
	source = ast.unparse(forget)
	assert source.index("clear_document_cache") < source.index("frappe.db.rollback()")
	outer = [t for t in forget.body if isinstance(t, ast.Try) and t.finalbody]
	assert outer and "frappe.db.rollback()" in ast.unparse(outer[0].finalbody[0])


def test_nothing_replaces_or_deletes_an_existing_chart():
	with open(os.path.join(ACCOUNTING, "setup.py"), encoding="utf-8") as f:
		source = f.read()
	assert "delete_doc" not in source
	assert not re.search(r"db\.delete\(", source)
	assert "replace_existing" not in source


def test_no_commit_anywhere_in_the_app():
	found = []
	for root, _dirs, files in os.walk(os.path.join(REPO, "erpcm")):
		for name in files:
			if not name.endswith(".py"):
				continue
			path = os.path.join(root, name)
			for node in ast.walk(parse(path)):
				# any `<something>.commit(...)`, which also catches `db = frappe.db; db.commit()`
				if (
					isinstance(node, ast.Call)
					and isinstance(node.func, ast.Attribute)
					and node.func.attr == "commit"
				):
					found.append(f"{os.path.relpath(path, REPO)}:{node.lineno}")
				# SQL that commits: sql("commit"), sql("COMMIT WORK"), ...
				if (
					isinstance(node, ast.Constant)
					and isinstance(node.value, str)
					and re.match(r"\s*commit\b", node.value, re.IGNORECASE)
				):
					found.append(f"{os.path.relpath(path, REPO)}:{node.lineno}")
	assert not found, found
