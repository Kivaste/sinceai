"""No cache keyed on object identity in src/ (AGENTS.md: a defect class found twice becomes a guard; #149, #148 r3).

An ``id(obj)`` key outlives ``obj``: once the object is freed, a new object can get the same id and read the old
entry. Two rules, scanned with the AST over the real src tree:

Rows (trigger -> result):
  any call of the builtin id(...) in src/ (a key, a tuple key, a dict literal key, anywhere)  -> violation
  a call of a kit scorer that caches on id() (pets_eval u1_intent / u5_vocab) in a function that
  does not empty that scorer's _CACHE first                                                    -> violation
  the kit scorer called after <module>._CACHE.clear() in the same function                     -> allowed
  a locally defined function named id, or an attribute .id(...)                                -> not the builtin

Allowlist: none (src/ has no id() call today). The planted-module tests prove each rule can fail.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
# pets_eval functions that key pets_eval.utility.customer_service._CACHE on ("...", id(frame), len(frame))
KIT_ID_CACHED = {"u1_intent", "u5_vocab"}


def _clears_cache(fn: ast.AST, call: ast.Call) -> bool:
    """True if ``fn`` calls ``<x>._CACHE.clear()`` on a line before ``call``."""
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "clear"
                and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "_CACHE"
                and n.lineno <= call.lineno):
            return True
    return False


def scan_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    shadowed = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))} & {"id"}
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "id" and not shadowed:
            bad.append(f"{path.name}:{n.lineno} id() call")
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            continue
        body = fn.body
        for stmt in body:
            for n in ast.walk(stmt):
                if not isinstance(n, ast.Call):
                    continue
                f = n.func
                name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
                if name in KIT_ID_CACHED and not _clears_cache(fn, n):
                    bad.append(f"{path.name}:{n.lineno} {name} without _CACHE.clear()")
    return sorted(set(bad))


def scan_tree(root: Path) -> list[str]:
    return [b for p in sorted(root.rglob("*.py")) for b in scan_file(p)]


def test_src_has_no_identity_keyed_cache():
    assert scan_tree(SRC) == []


def test_scan_flags_an_id_keyed_dict(tmp_path):
    (tmp_path / "a.py").write_text("_C = {}\ndef f(df):\n    key = ('u', id(df), len(df))\n    _C[key] = 1\n"
                                   "def g(x):\n    return {id(x): x}\n")
    assert scan_tree(tmp_path) == ["a.py:3 id() call", "a.py:6 id() call"]


def test_scan_flags_a_kit_id_cached_scorer_called_without_clearing(tmp_path):
    (tmp_path / "a.py").write_text("from pets_eval.utility import customer_service as cs\n"
                                   "def f(o, p):\n    return cs.u5_vocab(o, p)\n"
                                   "from pets_eval.utility.customer_service import u1_intent\n"
                                   "def g(o, p):\n    return u1_intent(o, p)\n")
    assert scan_tree(tmp_path) == ["a.py:3 u5_vocab without _CACHE.clear()", "a.py:6 u1_intent without _CACHE.clear()"]


def test_scan_allows_a_kit_scorer_after_clearing_its_cache(tmp_path):
    (tmp_path / "a.py").write_text("from pets_eval.utility import customer_service as cs\n"
                                   "def f(o, p):\n    cs._CACHE.clear()\n    return cs.u5_vocab(o, p)\n")
    assert scan_tree(tmp_path) == []


def test_scan_ignores_a_local_id_function_and_attribute_id(tmp_path):
    (tmp_path / "a.py").write_text("def id(x):\n    return x\nid(1)\n")
    (tmp_path / "b.py").write_text("def f(o):\n    return o.id(1)\n")
    assert scan_tree(tmp_path) == []
