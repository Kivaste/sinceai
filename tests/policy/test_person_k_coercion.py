"""No code in ``pets_release.minimiser`` turns a missing measurement into a neutral or perfect score (#112, #118).

This defect class turned up twice: in risk (#112, a missing PersonK scored as perfect privacy) and in search (#118,
a missing PersonK read as 0.0 shortfall). This AST scan of src/pets_release/minimiser/ fails on new instances.
A missing PersonK / k measurement must raise or refuse.

Rows (trigger -> result):
  None check (``x is None``, ``not x``, inside an ``or`` test) yielding a numeric constant
      (``if x is None: return 0.0``, ``0.0 if x is None else x``, ``x = 0`` under it)      -> violation
  None check of a PersonK / k name (pk, person_k, k, shortfall, ...) followed by
      ``break`` / ``continue``                                                               -> violation
  ``x or <number>`` (``units or 0``)                                                         -> violation
  ``.get("<k key>", <number>)`` / ``getattr(x, "<k name>", <number>)``                       -> violation
  a PersonK / k parameter with a numeric default (``def f(k=5)``)                            -> violation
  infinity (``float("inf")``, ``math.inf``, ``np.inf``)                                     -> violation
  ``max(..., default=...)`` / ``min(..., default=...)`` (a neutral value over an empty set)  -> violation
  ``if pk is None: raise ...``, ``if self.k is None: return None``, ``params or {}``         -> allowed
The production scan runs over the real minimiser package with an empty allowlist; the planted-file tests prove
each rule can fail.
"""
from __future__ import annotations

import ast
from pathlib import Path

MINIMISER = Path(__file__).resolve().parents[2] / "src" / "pets_release" / "minimiser"
PK_NAMES = frozenset({"pk", "person_k", "personk", "k", "shortfall", "sh", "units_before", "qi_k_shortfall",
                      "qi_unique_rate", "per_person", "unidentified"})
ALLOWLIST: frozenset[str] = frozenset()  # "<file>:<rule>:<function>" entries; each needs a written justification


def _num(node) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return isinstance(node, ast.Constant) and type(node.value) in (int, float)


def _name(node) -> str | None:
    """The last name of ``x``, ``self.x`` or ``ev["x"]``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None


def _none_checked(test) -> list:
    """Expressions a test treats as missing: ``x is None``, ``x == None``, any operand of an ``or``, and ``not x``
    for a PersonK / k name (``not sens`` on a list of released columns is a real empty set, not a missing value)."""
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        return [x for v in test.values for x in _none_checked(v)]
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Is, ast.Eq)) \
            and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None:
        return [test.left]
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and _pk([test.operand]):
        return [test.operand]
    return []


def _pk(nodes) -> bool:
    return any((_name(n) or "").lower() in PK_NAMES for n in nodes)


def _yields_number(stmts) -> bool:
    for s in stmts[:1]:  # the statement the None branch runs first
        if isinstance(s, ast.Return) and s.value is not None and _num(s.value):
            return True
        if isinstance(s, (ast.Assign, ast.AnnAssign)) and s.value is not None and _num(s.value):
            return True
    return False


def scan_source(text: str, fname: str = "<src>") -> list[str]:
    tree = ast.parse(text, filename=fname)
    func_of = {}
    for f in ast.walk(tree):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(f):
                func_of.setdefault(id(n), f.name)  # outermost first; nested defs keep the enclosing name
    bad = []

    def hit(node, rule):
        key = f"{fname}:{rule}:{func_of.get(id(node), '<module>')}"
        if key not in ALLOWLIST:
            bad.append(f"{fname}:{node.lineno} {rule}")

    for n in ast.walk(tree):
        if isinstance(n, ast.If):
            checked = _none_checked(n.test)
            if checked and _yields_number(n.body):
                hit(n, "none-to-number")
            if checked and _pk(checked) and isinstance(n.body[0], (ast.Break, ast.Continue)):
                hit(n, "missing-k-skipped")
        elif isinstance(n, ast.IfExp):
            if _none_checked(n.test) and _num(n.body):
                hit(n, "none-to-number")
        elif isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or):
            if any(_num(v) for v in n.values[1:]):
                hit(n, "or-number")
        elif isinstance(n, ast.Call):
            f = n.func
            fname_ = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if fname_ == "get" and len(n.args) == 2 and _num(n.args[1]) and _pk([n.args[0]]):
                hit(n, "get-k-default")
            if fname_ == "get" and len(n.args) == 2 and _num(n.args[1]) and isinstance(n.args[0], ast.Constant) \
                    and str(n.args[0].value).lower() in PK_NAMES:
                hit(n, "get-k-default")
            if fname_ == "getattr" and len(n.args) == 3 and _num(n.args[2]) and isinstance(n.args[1], ast.Constant) \
                    and str(n.args[1].value).lower() in PK_NAMES:
                hit(n, "get-k-default")
            if fname_ in ("max", "min") and any(k.arg == "default" for k in n.keywords):
                hit(n, "max-min-default")
            if fname_ == "float" and n.args and isinstance(n.args[0], ast.Constant) \
                    and str(n.args[0].value).strip().lstrip("+-").lower() in ("inf", "infinity"):
                hit(n, "infinity")
        elif isinstance(n, ast.Attribute) and n.attr in ("inf", "infty", "Inf", "PINF", "NINF"):
            hit(n, "infinity")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = n.args
            pos = a.posonlyargs + a.args
            pairs = list(zip(pos[len(pos) - len(a.defaults):], a.defaults)) + \
                [(x, d) for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None]
            for arg, d in pairs:
                if arg.arg.lower() in PK_NAMES and _num(d):
                    hit(n, "k-default-arg")
    return bad


def scan_tree(root: Path) -> list[str]:
    return [b for p in sorted(root.rglob("*.py")) for b in scan_source(p.read_text(encoding="utf-8-sig"), p.name)]


def test_minimiser_has_no_missing_measurement_coercion():
    assert MINIMISER.is_dir()
    assert scan_tree(MINIMISER) == []


def test_allowlist_is_empty():
    assert ALLOWLIST == frozenset()  # any entry must come with a written justification in this file


PLANTED = {
    "none-to-number": [
        "def f(ev):\n    pk = ev['pk']\n    if pk is None:\n        return 0.0\n    return 1.0\n",
        "def f(rv):\n    return {c: (0.0 if v is None else v) for c, v in rv.items()}\n",
        "def f(df):\n    if df is None or len(df) == 0:\n        return 0.0\n",
        "def f(pk):\n    if not pk:\n        x = 0\n    return x\n",
        "def f(pk):\n    if pk == None:\n        return -1\n",
    ],
    "missing-k-skipped": [
        "def f(R):\n    while True:\n        pk = R()\n        if pk is None:\n            break\n",
        "def f(xs):\n    for ev in xs:\n        if ev['pk'] is None:\n            continue\n",
        "def f(self):\n    while True:\n        if self.shortfall is None:\n            break\n",
    ],
    "or-number": ["def f(units_before):\n    return int(units_before or 0)\n", "x = y or 0.0\n"],
    "get-k-default": ["def f(ev):\n    return ev.get('qi_k_shortfall', 0.0)\n",
                      "def f(o):\n    return getattr(o, 'k', 1)\n"],
    "k-default-arg": ["def f(policy, k=5):\n    return k\n", "def f(*, pk=0):\n    return pk\n"],
    "infinity": ["import math\nK = math.inf\n", "k = float('inf')\n", "import numpy as np\nk = np.inf\n"],
    "max-min-default": ["def f(vals):\n    return max(vals, default=0.0)\n"],
}


def test_planted_patterns_are_found():
    for rule, srcs in PLANTED.items():
        for src in srcs:
            got = scan_source(src, "planted.py")
            assert any(rule in b for b in got), (rule, src, got)


def test_planted_file_in_a_tree_is_found(tmp_path):
    (tmp_path / "ok.py").write_text("def f(pk):\n    if pk is None:\n        raise RuntimeError('PersonK missing')\n",
                                    encoding="utf-8")
    assert scan_tree(tmp_path) == []
    (tmp_path / "planted.py").write_text(PLANTED["none-to-number"][0], encoding="utf-8")
    assert scan_tree(tmp_path) == ["planted.py:3 none-to-number"]


def test_fail_closed_forms_are_allowed():
    ok = (
        "def f(self, ev):\n    if self.k is None:\n        return None\n    pk = ev['pk']\n"
        "    if pk is None:\n        raise RuntimeError('PersonK missing')\n    return 1.0\n"
        "def g(params, log):\n    return (params or {}), list(log or [])\n"
        "def s(sens):\n    if not sens:\n        return 0.0\n"
        "def h(rs, key):\n    for r in rs:\n        pr = r.get(key)\n        if pr is None:\n            continue\n"
    )
    assert scan_source(ok) == []
