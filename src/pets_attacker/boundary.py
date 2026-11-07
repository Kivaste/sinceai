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

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ATTACKER = "pets_attacker"
PACKAGE = "pets_release"
_TRUTH_RE = re.compile(r"""(^|[\\/'"])truth([\\/'"]|$)""", re.MULTILINE)


# The kit adapter names `truth` only to forbid it; exempt from the truth-text scan (not the
# attacker-name scan, not the runtime guard).
TRUTH_SCAN_EXEMPT = frozenset({"pets_release/kit.py"})


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


def _scan(src: Path, pattern, *, inside_attacker: bool = False, exempt=frozenset()) -> list[str]:
    out = []
    for p in _py_files(src, inside_attacker=inside_attacker):
        if p.relative_to(src).as_posix() in exempt:
            continue
        t = _text(p)
        if t is None or pattern(t):  # unreadable = violation
            out.append(str(p))
    return out


def truth_references(src: Path) -> list[str]:
    """Files outside the attacker package naming a `truth` path segment (or unreadable)."""
    return _scan(src, lambda t: bool(_TRUTH_RE.search(t)), exempt=TRUTH_SCAN_EXEMPT)


def attacker_importers(src: Path) -> list[str]:
    """Files outside the attacker package mentioning `pets_attacker` at all (or unreadable)."""
    return _scan(src, lambda t: ATTACKER in t)


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
        res = json.loads(line[len("RESULT"):])
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


