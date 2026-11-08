"""Must-fix #82: every CLI / module entry point installs the offline guard, for itself and its children.

Each case runs the real entry point in a fresh interpreter whose environment carries no guard
(`cli_env` drops PETS_OFFLINE and the hook path), then plants a socket attempt in that same process
and in a child it starts. Both must be blocked. Synthetic, content-free: usage-error arguments only.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import PYTHON, SRC, cli_env

PROBE = (
    "import socket,sys\n"
    "try:\n"
    "    socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
    "except Exception:\n"
    "    print('BLOCKED'); sys.exit(0)\n"
    "print('OPEN'); sys.exit(1)\n"
)

# `python -m <module>`: the module route, run exactly as the interpreter does.
MODULES = [
    "pets_release",
    "pets_release.checks",
    "pets_release.manifest",
    "pets_release.contract",
    "pets_release.redaction_eval",
    "pets_attacker",
    "pets_attacker.bridge",
    "pets_release.measure.wire",
    "pets_release.ui",
]
# `<module>.main(argv)` called directly (e.g. from Python, or by the dispatcher).
MAINS = [
    "pets_release.cli",
    "pets_release.checks.__main__",
    "pets_release.manifest.__main__",
    "pets_release.contract.__main__",
    "pets_release.redaction_eval.__main__",
    "pets_attacker.cli",
    "pets_attacker.bridge",
    "pets_release.dashboard.cli",
    "pets_release.evidence_pack.cli",
    "pets_release.detect.cli",
    "pets_release.verify.cli",
    "pets_release.run.cli",
    "pets_release.submission.cli",
    "pets_release.measure.wire",
    "pets_release.llm.cli",  # guarded: offline unless --allow-network (tests/offline/test_llm_exemption.py)
]

# The only entry point allowed to open a socket. It is not guarded; it is gated: it is spawned solely by
# `pets_release.llm.transport.subprocess_transport`, which only the `draft-policy` CLI calls, only under
# `--allow-network` (ADR 0002). tests/offline/test_llm_exemption.py fails if that gate is removed.
EXEMPT = {
    "pets_release.llm.sender": "sends the one LLM request; spawned only by the CLI under --allow-network",
}

_AFTER = (
    "import subprocess, sys\n"
    f"p = subprocess.run([sys.executable, '-c', {PROBE!r}], capture_output=True, text=True)\n"
    "print(p.stdout.strip())\n"
    f"exec({PROBE!r})\n"
)


def _probe(entry: str, tmp_path) -> list[str]:
    code = (
        "import sys\n"
        "try:\n"
        f"{entry}"
        "except BaseException:\n"
        "    pass\n"
        "sys.stdout.flush()\n"
        "print('---')\n" + _AFTER
    )
    r = subprocess.run([PYTHON, "-c", code], cwd=tmp_path, env=cli_env(), capture_output=True, text=True,
                       encoding="utf-8", check=False)
    tail = r.stdout.split("---")[-1].split()
    return tail


@pytest.mark.parametrize("module", MODULES)
def test_module_entry_point_blocks_sockets_in_process_and_children(module, tmp_path):
    entry = (f"    sys.argv = [{module!r}, '--no-such-flag']\n"
             f"    import runpy; runpy.run_module({module!r}, run_name='__main__', alter_sys=True)\n")
    assert _probe(entry, tmp_path) == ["BLOCKED", "BLOCKED"]


@pytest.mark.parametrize("module", MAINS)
def test_direct_main_call_blocks_sockets_in_process_and_children(module, tmp_path):
    entry = f"    import importlib; importlib.import_module({module!r}).main(['--no-such-flag'])\n"
    assert _probe(entry, tmp_path) == ["BLOCKED", "BLOCKED"]


def test_control_without_an_entry_point_the_probe_opens_a_socket(tmp_path):
    """Planted control: the harness itself does not block, so a pass above is the entry point's doing."""
    assert _probe("    pass\n", tmp_path) == ["OPEN", "OPEN"]


def _entry_points(src: Path = SRC) -> tuple[set[str], set[str]]:
    """Every `def main` and every `__main__.py` under src/, found by parsing the source."""
    mains, modules = set(), set()
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).with_suffix("")
        name = ".".join(rel.parts)
        if path.name == "__main__.py":
            modules.add(".".join(rel.parts[:-1]))
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        if any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body):
            mains.add(name)
        if any(isinstance(n, ast.If) and "__main__" in ast.unparse(n.test) for n in tree.body):
            modules.add(name)
    return mains, modules


def test_every_entry_point_in_src_is_covered_by_a_case_above():
    mains, modules = _entry_points()
    assert mains == set(MAINS) | set(EXEMPT)
    assert modules == set(MODULES) | set(EXEMPT) | {"pets_release.cli", "pets_release.checks.__main__",
                                                    "pets_release.manifest.__main__",
                                                    "pets_release.contract.__main__",
                                                    "pets_release.redaction_eval.__main__"}


def test_completeness_scan_sees_planted_entry_points(tmp_path):
    """Planted-file test for the scan: a new main() or __main__.py is found, so it cannot go uncovered."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "tool.py").write_text("def main(argv):\n    return 0\n", encoding="utf-8")
    (pkg / "__main__.py").write_text("print('x')\n", encoding="utf-8")
    (pkg / "helper.py").write_text("def helper():\n    pass\n", encoding="utf-8")
    assert _entry_points(tmp_path) == ({"pkg.tool"}, {"pkg"})
