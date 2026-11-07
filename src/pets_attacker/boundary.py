"""Truth-boundary and import-graph guards. Both fail closed.

(a) Static: no Python file under src/ outside pets_attacker/ may contain the substring
    ``pets_attacker`` or a ``truth`` path-segment literal (raw-text regex; an unreadable
    file is a violation; a missing or empty scan root is an error).
(b) Runtime: in a clean subprocess, import every ``pets_release`` module (walk_packages)
    and require that ``pets_attacker`` never entered ``sys.modules`` and that no file
    under the kit's truth/ directory was opened (audit hook on ``open``). The hook fails closed:
    an ``open`` it cannot resolve (unknown target type, or any error inside the hook) is refused,
    recorded as ``hook-error``, and makes the child exit non-zero (``runtime-check-failed``).

Residual risk: import names or paths computed at runtime are covered by (b) only for
code paths exercised at import time.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pets_release.manifest.canonical import loads_strict

ATTACKER = "pets_attacker"
PACKAGE = "pets_release"
_TRUTH_RE = re.compile(r"""(^|[\\/'"])truth([\\/'"]|$)""", re.MULTILINE)


# The kit adapter names `truth` only to forbid it; exempt from the truth-text scan (not the
# attacker-name scan, not the runtime guard).
TRUTH_SCAN_EXEMPT = frozenset({"pets_release/kit.py"})


# #138: the measured run starts the attacker as a separate child process from this one file. Structural allowlist
# (round 2): the file names the attacker only in exactly two top-level assignments (LAUNCHER_ASSIGNMENTS), and uses
# those two names only as the third element of ``[sys.executable, "-m", <NAME>, ...]`` passed as the only
# positional argument of ``subprocess.run`` (no executable=, shell= or **kwargs). ``subprocess``, ``sys`` and the
# two names are never rebound or shadowed. Every other mention or use, any dynamic-import or exec route, and an
# unparseable or unreadable file are violations. The truth scan and the runtime guard are unchanged for it.
ATTACKER_LAUNCHER = "pets_release/measure/attackers.py"
LAUNCHER_ASSIGNMENTS = {"ATTACKER_MODULE": ATTACKER, "BRIDGE_MODULE": ATTACKER + ".bridge"}
_LAUNCH_MODULES = ("subprocess", "sys")
_PINNED = frozenset({*_LAUNCH_MODULES, *LAUNCHER_ASSIGNMENTS})
_DYNAMIC = frozenset({"importlib", "__import__", "import_module", "runpy", "run_module", "run_path", "pkgutil",
                      "exec", "eval", "compile", "builtins", "__builtins__"})


def _is_name(node, name: str | None = None) -> bool:
    import ast

    return isinstance(node, ast.Name) and (name is None or node.id == name)


def _launch_use(node):
    """The ``<NAME>`` node of an approved ``subprocess.run([sys.executable, "-m", <NAME>, ...])`` call, else None."""
    import ast

    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run"
            and _is_name(node.func.value, "subprocess") and len(node.args) == 1 and isinstance(node.args[0], ast.List)):
        return None
    if any(k.arg in (None, "executable", "shell") for k in node.keywords):
        return None
    elts = node.args[0].elts
    if len(elts) < 3 or not (isinstance(elts[0], ast.Attribute) and elts[0].attr == "executable"
                             and _is_name(elts[0].value, "sys")):
        return None
    if not (isinstance(elts[1], ast.Constant) and elts[1].value == "-m"):
        return None
    name = elts[2]
    return name if _is_name(name) and name.id in LAUNCHER_ASSIGNMENTS and isinstance(name.ctx, ast.Load) else None


def _binds_pinned(node) -> bool:
    """global/nonlocal, a parameter, a def/class, an ``except ... as`` or a match capture naming a pinned name.
    Import aliases are checked separately (``ast.alias.name`` is the imported module, not a binding)."""
    import ast

    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return bool(set(node.names) & _PINNED)
    if isinstance(node, ast.arg):
        return node.arg in _PINNED
    return not isinstance(node, ast.alias) and getattr(node, "name", None) in _PINNED


def _launcher_violates(text: str) -> bool:
    import ast

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return True
    if text.count(ATTACKER) != len(LAUNCHER_ASSIGNMENTS):  # comments, docstrings and other strings included
        return True
    defined = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(_is_name(t) and t.id in LAUNCHER_ASSIGNMENTS for t in node.targets):
            t = node.targets[0]
            if (len(node.targets) != 1 or not _is_name(t) or t.id in defined or not isinstance(node.value, ast.Constant)
                    or node.value.value != LAUNCHER_ASSIGNMENTS[t.id]):
                return True
            defined[t.id] = t
    if set(defined) != set(LAUNCHER_ASSIGNMENTS):
        return True
    allowed_stores = {id(t) for t in defined.values()}
    allowed_loads = {id(u) for u in map(_launch_use, ast.walk(tree)) if u is not None}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _PINNED:
            if not isinstance(node.ctx, ast.Load):
                if id(node) not in allowed_stores:
                    return True  # rebinding, deleting or shadowing a pinned name
            elif node.id in LAUNCHER_ASSIGNMENTS and id(node) not in allowed_loads:
                return True  # a module-name constant used anywhere but the approved launch position
        elif isinstance(node, ast.Attribute) and not isinstance(node.ctx, ast.Load) and _is_name(node.value) \
                and node.value.id in _LAUNCH_MODULES:
            return True  # e.g. ``subprocess.run = ...`` or ``sys.executable = ...``
        elif _binds_pinned(node):
            return True
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] + ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            if any(m.split(".")[0] in _DYNAMIC for m in mods):
                return True
            for a in node.names:
                bound = a.asname or a.name.split(".")[0]
                plain = isinstance(node, ast.Import) and a.asname is None and a.name in _LAUNCH_MODULES
                if bound in _PINNED and not plain:
                    return True
        elif getattr(node, "id", None) in _DYNAMIC or getattr(node, "attr", None) in _DYNAMIC:
            return True  # a Name or Attribute naming a dynamic-import or exec route
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in _DYNAMIC:
            return True  # e.g. getattr(builtins, "__import__")
    return False


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


def _text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def _scan(src: Path, pattern, *, inside_attacker: bool = False, exempt=frozenset(), special=None) -> list[str]:
    out = []
    for p in _py_files(src, inside_attacker=inside_attacker):
        rel = p.relative_to(src).as_posix()
        if rel in exempt:
            continue
        t = _text(p)
        check = special.get(rel, pattern) if special else pattern
        if t is None or check(t):  # unreadable = violation
            out.append(str(p))
    return out


def truth_references(src: Path) -> list[str]:
    """Files outside the attacker package naming a `truth` path segment (or unreadable)."""
    return _scan(src, lambda t: bool(_TRUTH_RE.search(t)), exempt=TRUTH_SCAN_EXEMPT)


def attacker_importers(src: Path) -> list[str]:
    """Files outside the attacker package mentioning `pets_attacker` at all (or unreadable). The one launcher
    file (#138) may name it only as its exact module-name constants."""
    return _scan(src, lambda t: ATTACKER in t, special={ATTACKER_LAUNCHER: _launcher_violates})


def attacker_reads_truth(src: Path) -> bool:
    """Sanity: the attacker package itself is the one place that does."""
    return any((t := _text(p)) is not None and _TRUTH_RE.search(t)
               for p in _py_files(src, inside_attacker=True))


_CHILD = r"""
import importlib, json, os, pkgutil, sys
truth = os.path.normcase(os.path.realpath(sys.argv[1]))
opened = []
hook_errors = []
def hook(event, args):
    if event != "open":
        return
    # Fail closed: an open the hook cannot resolve (unknown target type, decode/resolve error) is refused.
    # An int fd opens no new path: it wraps a pipe/socket or an fd from an os.open whose path was already
    # audited here, so it is allowed (subprocess pipes at import time use it).
    try:
        if args and type(args[0]) is int:
            return
        if not args or not isinstance(args[0], (str, bytes, os.PathLike)):
            raise TypeError("unresolvable open target")
        p = os.path.normcase(os.path.realpath(os.fsdecode(args[0])))
    except BaseException:
        hook_errors.append(1)
        raise PermissionError("boundary audit hook refused an unresolvable open") from None
    if p == truth or p.startswith(truth + os.sep):
        opened.append(1)
sys.addaudithook(hook)
errors = []
n = 0
pkg = importlib.import_module(sys.argv[2])
mods = [sys.argv[2]]
for m in pkgutil.walk_packages(pkg.__path__, sys.argv[2] + ".", onerror=lambda name: errors.append(name)):
    if not m.name.endswith(".__main__"):  # entry points run main() on import; the static scan covers them
        mods.append(m.name)
for name in mods:
    try:
        importlib.import_module(name)
        n += 1
    except BaseException:
        errors.append(name)
print("RESULT" + json.dumps({
    "imported": n,
    "errors": sorted(set(errors)),
    "attacker": sorted(k for k in sys.modules if k.split(".")[0] == sys.argv[3]),
    "truth_opened": bool(opened),
    "hook_errors": len(hook_errors),
}))
sys.exit(3 if hook_errors else 0)
"""


def runtime_violations(src: Path, truth_dir: Path) -> list[str]:
    """Import every pets_release module in a clean subprocess; list boundary violations (names only)."""
    src = Path(src).resolve()
    if not (src / PACKAGE / "__init__.py").is_file():
        raise BoundaryError(f"{PACKAGE} not found under the scan root")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONSTARTUP")}
    env.update(PYTHONPATH=str(src), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    with tempfile.TemporaryDirectory() as cwd:
        try:
            r = subprocess.run([sys.executable, "-c", _CHILD, str(truth_dir), PACKAGE, ATTACKER],
                               cwd=cwd, env=env, capture_output=True, text=True, timeout=600, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return ["runtime-check-failed"]
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("RESULT")), None)
    if line is None:
        return ["runtime-check-failed"]
    try:
        res = loads_strict(line[len("RESULT"):])  # #131: the child's record parses strictly, never last-wins
        out = [f"import-error:{m}" for m in res["errors"]]
        if res["attacker"]:
            out.append("attacker-loaded")
        if res["truth_opened"]:
            out.append("truth-opened")
        if res["hook_errors"] != 0:
            out.append("hook-error")
    except (ValueError, KeyError, TypeError):
        return ["runtime-check-failed"]
    if r.returncode != 0:
        out.append("runtime-check-failed")
    return out


