"""Truth-boundary and import-graph guards: AST scan of src/*.py."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ATTACKER = "pets_attacker"
_TRUTH_RE = re.compile(r"(^|[\\/])truth([\\/]|$)")


def _py_files(src: Path, *, inside_attacker: bool):
    for p in sorted(src.rglob("*.py")):
        rel = p.relative_to(src).parts
        if (rel[0] == ATTACKER) == inside_attacker:
            yield p


def _parse(p: Path):
    try:
        return ast.parse(p.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _is_docstring(tree: ast.AST, node: ast.Constant) -> bool:
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            body = parent.body
            if body and isinstance(body[0], ast.Expr) and body[0].value is node:
                return True
    return False


def _raw(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


def _truth_hits(p: Path) -> bool:
    tree = _parse(p)
    if tree is None:  # fail closed: unparseable file is scanned as text
        return bool(re.search(r"[\\'\"/\\\\]truth[\\'\"/\\\\]", _raw(p)))
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and not _is_docstring(tree, n):
            if n.value == "truth" or _TRUTH_RE.search(n.value):
                return True
    return False


def truth_references(src: Path) -> list[str]:
    """Files outside the attacker package that name a `truth` path segment."""
    return [str(p) for p in _py_files(src, inside_attacker=False) if _truth_hits(p)]


def attacker_reads_truth(src: Path) -> bool:
    """Sanity: the attacker package itself is the one place that does."""
    return any(_truth_hits(p) for p in _py_files(src, inside_attacker=True))


def _imports_attacker(p: Path) -> bool:
    tree = _parse(p)
    if tree is None:  # fail closed
        return ATTACKER in _raw(p)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] == ATTACKER for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and n.level == 0 and (n.module or "").split(".")[0] == ATTACKER:
            return True
        if isinstance(n, ast.Call):
            fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if fn in ("import_module", "__import__") and n.args:
                a = n.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.split(".")[0] == ATTACKER:
                    return True
    return False


def attacker_importers(src: Path) -> list[str]:
    """Files outside the attacker package that import it."""
    return [str(p) for p in _py_files(src, inside_attacker=False) if _imports_attacker(p)]


