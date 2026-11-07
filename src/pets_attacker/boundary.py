"""Truth-boundary and import-graph guards: AST scan of src/*.py. Fails closed.

- A missing or empty scan root is an error, never "no hits".
- An unparseable file outside the attacker is a violation.
- Dynamic imports (`import_module`, `__import__`) must resolve to a literal or a
  module-level string constant; anything else is a violation, except the sites in
  ALLOWED_DYNAMIC, which are also required never to mention the attacker at all.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ATTACKER = "pets_attacker"
_TRUTH_RE = re.compile(r"(^|[\\/])truth([\\/]|$)")
# Package-relative (posix) files that discover their own sub-modules dynamically.
ALLOWED_DYNAMIC = frozenset({"pets_release/checks/registry.py", "pets_release/cli.py"})


class BoundaryError(ValueError):
    """The scan could not be performed (bad root)."""


def _py_files(src: Path, *, inside_attacker: bool):
    src = Path(src)
    files = sorted(src.rglob("*.py")) if src.is_dir() else []
    if not files:
        raise BoundaryError("scan root missing or contains no Python files")
    for p in files:
        if (p.relative_to(src).parts[0] == ATTACKER) == inside_attacker:
            yield p


def _raw(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


def _parse(p: Path):
    try:
        return ast.parse(_raw(p))
    except (SyntaxError, ValueError):
        return None


def _docstring_nodes(tree: ast.AST) -> set:
    out = set()
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            body = parent.body
            if body and isinstance(body[0], ast.Expr):
                out.add(id(body[0].value))
    return out


def _truth_hits(p: Path, *, unparseable_is_hit: bool) -> bool:
    tree = _parse(p)
    if tree is None:
        return unparseable_is_hit
    docs = _docstring_nodes(tree)
    for n in ast.walk(tree):
        if (isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
                and (n.value == "truth" or _TRUTH_RE.search(n.value))):
            return True
    return False


def truth_references(src: Path) -> list[str]:
    """Files outside the attacker package that name a `truth` path segment (or cannot be parsed)."""
    return [str(p) for p in _py_files(src, inside_attacker=False) if _truth_hits(p, unparseable_is_hit=True)]


def attacker_reads_truth(src: Path) -> bool:
    """Sanity: the attacker package itself is the one place that does."""
    return any(_truth_hits(p, unparseable_is_hit=False) for p in _py_files(src, inside_attacker=True))


def _constants(tree: ast.AST) -> dict:
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = n.value.value
        elif (isinstance(n, ast.AnnAssign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
              and isinstance(n.target, ast.Name)):
            out[n.target.id] = n.value.value
    return out


def _is_attacker(name: str) -> bool:
    return name.split(".")[0] == ATTACKER


def _imports_attacker(p: Path, rel: str) -> bool:
    tree = _parse(p)
    if tree is None:
        return True  # fail closed
    consts = _constants(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(_is_attacker(a.name) for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and n.level == 0 and _is_attacker(n.module or ""):
            return True
        if isinstance(n, ast.Call):
            fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if fn not in ("import_module", "__import__"):
                continue
            arg = n.args[0] if n.args else next((k.value for k in n.keywords if k.arg in ("name", "package")), None)
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if _is_attacker(arg.value):
                    return True
            elif isinstance(arg, ast.Name) and arg.id in consts:
                if _is_attacker(consts[arg.id]):
                    return True
            elif rel in ALLOWED_DYNAMIC:
                if ATTACKER in _raw(p):
                    return True
            else:
                return True  # unresolvable dynamic import
    return False


def attacker_importers(src: Path) -> list[str]:
    """Files outside the attacker package that import it, import dynamically without a resolvable
    target, or cannot be parsed."""
    root = Path(src)
    return [str(p) for p in _py_files(src, inside_attacker=False)
            if _imports_attacker(p, p.relative_to(root).as_posix())]


