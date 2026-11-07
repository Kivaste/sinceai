"""The LLM front end's network path is gated, not unguarded (ADR 0002, must-fix #82 exemption).

`pets_release.llm.cli` is guarded like every other entry point. `pets_release.llm.sender` is the one explicit
exemption; these tests fail if the `--allow-network` gate in front of it is removed.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import PYTHON, SRC, cli_env

LLM = SRC / "pets_release" / "llm"

# Runs the real dispatcher (guard installed by it) with the transport replaced by a probe that records whether
# it was reached and whether a socket can be opened in this process.
_DRIVER = (
    "import socket, sys\n"
    "import pets_release.cli as top\n"
    "import pets_release.llm.cli as c\n"
    "seen = []\n"
    "def probe(url, body, key, timeout):\n"
    "    try:\n"
    "        socket.socket(); seen.append('open')\n"
    "    except OSError:\n"
    "        seen.append('blocked')\n"
    "    raise OSError('stop')\n"
    "orig = c.main\n"
    "c.main = lambda argv: orig(argv, transport=probe)\n"
    "rc = top.main(['draft-policy', '--request', 'x people', '--dataset', 'health', '--kit', sys.argv[1],\n"
    "               '--endpoint', 'http://127.0.0.1:9/v1', '--model', 'm'] + sys.argv[2:])\n"
    "print(rc, seen)\n"
)


def _drive(kit: Path, *extra: str) -> str:
    r = subprocess.run([PYTHON, "-c", _DRIVER, str(kit), *extra], env=cli_env(), capture_output=True,
                       text=True, encoding="utf-8", check=False)
    return r.stdout.strip()


def test_llm_cli_without_allow_network_never_reaches_the_transport(make_kit):
    assert _drive(make_kit()) == "2 []"


def test_llm_cli_with_allow_network_reaches_the_transport_but_its_own_process_stays_blocked(make_kit):
    assert _drive(make_kit(), "--allow-network") == "2 ['blocked']"


def _refs(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "llm.sender" in n.value:
            out.append("sender-module-string")
        if isinstance(n, ast.Name) and n.id == "subprocess_transport":
            out.append("subprocess_transport")
        if isinstance(n, ast.Attribute) and n.attr == "subprocess_transport":
            out.append("subprocess_transport")
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in n.names] + [getattr(n, "module", "") or ""]
            if any(x.endswith("sender") or x == "pets_release.llm.sender" for x in names):
                out.append("sender-import")
    return out


def test_sender_is_referenced_only_by_the_transport_and_the_transport_only_by_the_cli():
    scanned = 0
    for path in sorted((SRC / "pets_release").rglob("*.py")):
        scanned += 1
        refs = _refs(path)
        rel = path.relative_to(SRC).as_posix()
        if rel == "pets_release/llm/sender.py":
            continue
        if rel == "pets_release/llm/transport.py":
            assert "sender-module-string" in refs  # the one spawn site
        elif rel == "pets_release/llm/cli.py":
            assert "sender-module-string" not in refs and "sender-import" not in refs
        else:
            assert refs == [], (rel, refs)
    assert scanned > 20


def test_the_cli_passes_the_network_transport_only_after_the_allow_network_check():
    """Structural: in llm/cli.py main(), the `not a.allow_network` refusal precedes any use of `transport`."""
    tree = ast.parse((LLM / "cli.py").read_text(encoding="utf-8-sig"))
    (fn,) = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    gate = use = None
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and "allow_network" in ast.unparse(n.test) and any(
                isinstance(s, ast.Return) for s in n.body):
            gate = min(gate or n.lineno, n.lineno)
        if isinstance(n, ast.Name) and n.id == "transport" and isinstance(n.ctx, ast.Load):
            use = min(use or n.lineno, n.lineno)
    assert gate is not None and use is not None and gate < use
