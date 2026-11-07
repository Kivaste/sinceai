"""The gate text checks share no code with the redactor, detector, pseudonymiser or transforms."""
import ast
import os
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "src" / "pets_release" / "checks" / "text"
# Only the shared registry interface (ticket 04) may be imported from outside this package.
# ``checks._cues`` is the gate's own cue vocabulary shared with the cell rescans (#53); it must
# itself import only the stdlib (pinned below).
ALLOWED_FIRST_PARTY = ("pets_release.checks.text", "pets_release.checks.registry",
                       "pets_release.checks.records", "pets_release.checks._cues")
CUES = PKG.parent / "_cues.py"


def offending_imports(pkg_dir: Path, pkg_name: str = "pets_release.checks.text"):
    """Every import in pkg_dir that is neither stdlib nor inside pkg_name."""
    bad = []
    for path in sorted(pkg_dir.rglob("*.py")):
        rel = path.relative_to(pkg_dir).with_suffix("").parts
        mod_parts = pkg_name.split(".") + [p for p in rel if p != "__init__"]
        is_pkg = path.name == "__init__.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = mod_parts if is_pkg else mod_parts[:-1]
                    up = node.level - 1
                    if up > len(base) - len(pkg_name.split(".")):
                        bad.append((path.name, "relative import escapes package"))
                        continue
                    base = base[: len(base) - up] if up else base
                    names = [".".join(base + ([node.module] if node.module else []))]
                else:
                    names = [node.module or ""]
            for n in names:
                top = n.split(".")[0]
                if n.startswith(ALLOWED_FIRST_PARTY) or n == pkg_name:
                    continue
                if top in sys.stdlib_module_names or top == "__future__":
                    continue
                bad.append((path.name, n))
    return bad


def test_text_checks_import_only_stdlib_and_themselves():
    assert PKG.is_dir()
    assert offending_imports(PKG) == []


def test_shared_cue_module_imports_only_stdlib(tmp_path):
    pkg = tmp_path / "cues"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "_cues.py").write_text(CUES.read_text(encoding="utf-8"), encoding="utf-8")
    assert offending_imports(pkg, "cues") == []
    (pkg / "_cues.py").write_text(CUES.read_text(encoding="utf-8") + "\nimport pets_release.redactor\n",
                                  encoding="utf-8")
    assert offending_imports(pkg, "cues") == [("_cues.py", "pets_release.redactor")]


def test_planted_redactor_import_is_caught(tmp_path):
    pkg = tmp_path / "text"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import ok\n", encoding="utf-8")
    (pkg / "ok.py").write_text("import re\n", encoding="utf-8")
    (pkg / "bad_abs.py").write_text("from pets_release.redactor import pipeline\n", encoding="utf-8")
    (pkg / "bad_rel.py").write_text("from ...redactor import normalise\n", encoding="utf-8")
    (pkg / "bad_dep.py").write_text("import pandas\n", encoding="utf-8")
    bad = offending_imports(pkg)
    assert {b[0] for b in bad} == {"bad_abs.py", "bad_rel.py", "bad_dep.py"}


def test_importing_text_checks_loads_no_redactor_module():
    env = dict(os.environ, PYTHONPATH=str(PKG.parents[2]))
    code = (
        "import sys, pets_release.checks.text\n"
        "from pets_release.checks.registry import all_checks\n"
        "n=len([c for c in all_checks() if c.name.startswith('text.')])\n"
        "bad=[m for m in sys.modules if m.startswith(('pets_release.', 'pets_attacker')) and "
        "not m.startswith('pets_release.checks')]\n"
        "print(n, bad)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "14 []"
