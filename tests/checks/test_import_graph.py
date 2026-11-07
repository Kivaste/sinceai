"""The registry is an independent implementation: it imports nothing from detector, redactor or transforms."""
import ast
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
CHECKS = SRC / "pets_release" / "checks"
FORBIDDEN = ("pets_release.detect", "pets_release.redactor", "pets_release.ladders",
             "pets_release.pseudonym", "pets_release.minimiser", "pets_attacker")


def _bad(name):
    return any(name == f or name.startswith(f + ".") for f in FORBIDDEN)


def test_no_static_import_of_detector_redactor_or_transforms():
    hits = []
    files = sorted(CHECKS.rglob("*.py"))
    assert files
    for py in files:
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                hits += [(py.name, a.name) for a in node.names if _bad(a.name)]
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if node.level:  # relative: resolve against the file's package
                    pkg = py.relative_to(SRC).with_suffix("").parts[:-node.level]
                    mod = ".".join(pkg + ((mod,) if mod else ()))
                if _bad(mod) or any(_bad(f"{mod}.{a.name}") for a in node.names):
                    hits.append((py.name, mod))
    assert hits == []


def test_loaded_registry_pulls_no_forbidden_module():
    code = ("import sys, pets_release.checks as c; c.all_checks(); "
            "print('\\n'.join(sorted(sys.modules)))")
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    mods = r.stdout.split()
    assert "pets_release.checks.cells.labels" in mods
    assert [m for m in mods if _bad(m)] == []
