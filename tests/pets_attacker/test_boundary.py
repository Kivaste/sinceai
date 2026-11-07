"""Truth-boundary and import-graph guards.

Seams: (a) static raw-text scan of every file under src/ outside pets_attacker/;
(b) runtime import of every pets_release module in a subprocess.
Misses: truth paths or import names computed at runtime are only caught by (b),
and only on code paths exercised at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pets_attacker.boundary import (
    BoundaryError,
    attacker_importers,
    attacker_reads_truth,
    runtime_violations,
    truth_references,
)

SRC = Path(__file__).resolve().parents[2] / "src"


def _plant(root: Path, rel: str, text: str | bytes) -> None:
    p = root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- static guard
def test_real_tree_is_clean_and_attacker_reads_truth():
    assert attacker_reads_truth(SRC)
    assert truth_references(SRC) == []
    assert attacker_importers(SRC) == []


@pytest.mark.parametrize("text", [
    "import pets_attacker\n",
    "from pets_attacker.personas import broker_attack\n",
    'import importlib\nimportlib.import_module("pets_attacker")\n',
    'MOD = "pets_attacker"\n',
    "# pets_attacker\n",
    '"""mentions pets_attacker"""\n',
])
def test_any_mention_of_the_attacker_is_a_violation(tmp_path: Path, text):
    _plant(tmp_path, "pets_release/x.py", text)
    assert any(h.endswith("x.py") for h in attacker_importers(tmp_path / "src"))


@pytest.mark.parametrize("text", [
    'PATH = "truth/health__ed_visits.csv"\n',
    'p = root / "truth" / "x.csv"\n',
    'p = "kit\\\\truth\\\\x.csv"\n',
    "p = 'truth/x'\n",
])
def test_truth_path_segments_are_violations(tmp_path: Path, text):
    _plant(tmp_path, "pets_release/x.py", text)
    assert any(h.endswith("x.py") for h in truth_references(tmp_path / "src"))


def test_word_truth_in_prose_is_not_a_reference(tmp_path: Path):
    _plant(tmp_path, "pets_release/doc.py", '"""ground truth is not used here."""\nX = "the truth"\n')
    assert truth_references(tmp_path / "src") == []


def test_inside_attacker_is_allowed(tmp_path: Path):
    _plant(tmp_path, "pets_attacker/truth.py", 'from pets_attacker import b\nP = "truth/x.csv"\n')
    assert truth_references(tmp_path / "src") == []
    assert attacker_importers(tmp_path / "src") == []
    assert attacker_reads_truth(tmp_path / "src")


def test_non_python_and_odd_files_are_scanned_too_as_py_only_but_bom_and_unreadable_fail(tmp_path: Path):
    _plant(tmp_path, "pets_release/bom.py", b'\xef\xbb\xbfimport pets_attacker\nP = "truth/x.csv"\n')
    _plant(tmp_path, "pets_release/bad.py", b"\xff\xfe\x00\x80 not utf8")
    _plant(tmp_path, "pets_release/broken.py", "def (:\n")  # unparseable but readable and clean: fine for static text scan
    for fn in (attacker_importers, truth_references):
        hits = fn(tmp_path / "src")
        assert any(h.endswith("bom.py") for h in hits)
        assert any(h.endswith("bad.py") for h in hits)  # unreadable = violation


@pytest.mark.parametrize("fn", [attacker_importers, truth_references, attacker_reads_truth])
def test_missing_or_empty_scan_root_is_an_error(tmp_path: Path, fn):
    with pytest.raises(BoundaryError):
        fn(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(BoundaryError):
        fn(tmp_path / "empty")


# --------------------------------------------------------------- runtime guard
def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        _plant(tmp_path, rel, text)
    _plant(tmp_path, "pets_release/__init__.py", "")
    _plant(tmp_path, "pets_attacker/__init__.py", "")  # stub so a planted import can succeed
    return tmp_path / "src"


def _truth(tmp_path: Path) -> Path:
    d = tmp_path / "kit" / "truth"
    d.mkdir(parents=True)
    (d / "health__ed_visits.csv").write_text("record_id,person_id\n", encoding="utf-8")
    return d


def test_runtime_clean_tree_passes(tmp_path: Path):
    src = _tree(tmp_path, {"pets_release/a.py": "X = 1\n", "pets_release/sub/__init__.py": "", "pets_release/sub/b.py": "Y = 2\n"})
    assert runtime_violations(src, _truth(tmp_path)) == []


def test_runtime_catches_computed_attacker_import(tmp_path: Path):
    src = _tree(tmp_path, {"pets_release/sneak.py": 'import importlib\nimportlib.import_module("pets_" + "attacker")\n'})
    v = runtime_violations(src, _truth(tmp_path))
    assert any("attacker" in x for x in v)


def test_runtime_catches_truth_file_opened_at_import(tmp_path: Path):
    truth = _truth(tmp_path)
    p = str(truth / "health__ed_visits.csv").replace("\\", "/")
    src = _tree(tmp_path, {"pets_release/peek.py": f'open("{p}", encoding="utf-8").read()\n'})
    v = runtime_violations(src, truth)
    assert any("truth" in x for x in v)


def test_runtime_import_error_is_a_violation(tmp_path: Path):
    src = _tree(tmp_path, {"pets_release/boom.py": "raise RuntimeError('x')\n"})
    assert any("import-error" in x for x in runtime_violations(src, _truth(tmp_path)))


def test_runtime_missing_package_is_an_error(tmp_path: Path):
    _plant(tmp_path, "other/__init__.py", "")
    with pytest.raises(BoundaryError):
        runtime_violations(tmp_path / "src", _truth(tmp_path))


def test_runtime_does_not_leak_parent_modules(tmp_path: Path):
    """The subprocess starts clean: the already-loaded attacker in this process is irrelevant."""
    assert "pets_attacker" in sys.modules
    src = _tree(tmp_path, {"pets_release/a.py": "X = 1\n"})
    assert runtime_violations(src, _truth(tmp_path)) == []


def test_runtime_guard_on_the_real_tree(tmp_path: Path):
    """Until pets_release lands in this tree the guard must refuse, not pass; afterwards it must be clean."""
    truth = tmp_path / "truth"
    truth.mkdir()
    if (SRC / "pets_release" / "__init__.py").is_file():
        assert runtime_violations(SRC, truth) == []
    else:
        with pytest.raises(BoundaryError):
            runtime_violations(SRC, truth)


def test_main_entry_modules_are_not_executed_by_the_runtime_walk(tmp_path: Path):
    src = _tree(tmp_path, {"pets_release/__main__.py": "raise SystemExit(3)\n", "pets_release/a.py": "X = 1\n"})
    assert runtime_violations(src, _truth(tmp_path)) == []


# --- follow-up #77: the audit hook fails closed --------------------------------------------------------
# Rule: any error inside the hook, and any `open` it cannot resolve to a path (an int fd), is a violation,
# blocks that open, and makes the child exit non-zero. Rows: hook error -> open refused -> import error ->
# hook-error recorded -> child exit != 0 -> runtime-check-failed.
_SABOTAGE = (
    "import os, os.path\n"
    "def _boom(*a, **k):\n"
    "    raise RuntimeError('sabotaged')\n"
    "os.path.realpath = _boom\n"
    "open({p!r}, encoding='utf-8').read()\n"
)


def test_runtime_hook_error_fails_closed_and_blocks_the_open(tmp_path: Path):
    truth = _truth(tmp_path)
    p = str(truth / "health__ed_visits.csv")
    src = _tree(tmp_path, {"pets_release/peek.py": _SABOTAGE.format(p=p)})
    v = runtime_violations(src, truth)
    assert "hook-error" in v
    assert "import-error:pets_release.peek" in v  # the open was refused, so the import failed
    assert "runtime-check-failed" in v  # the child exited non-zero


def test_runtime_open_on_an_int_fd_is_a_violation(tmp_path: Path):
    other = tmp_path / "other.txt"
    other.write_text("x\n", encoding="utf-8")
    code = f"import os\nfd = os.open({str(other)!r}, os.O_RDONLY)\nopen(fd, encoding='utf-8').close()\n"
    src = _tree(tmp_path, {"pets_release/fd.py": code})
    v = runtime_violations(src, _truth(tmp_path))
    assert "hook-error" in v
    assert "runtime-check-failed" in v


def test_kit_module_is_exempt_from_the_truth_scan_only(tmp_path: Path):
    """pets_release/kit.py names `truth` to forbid it; the exemption is that one file, truth text only."""
    lit = 'FORBIDDEN = frozenset({"truth"})\n'
    _plant(tmp_path, "pets_release/kit.py", lit)
    _plant(tmp_path, "pets_release/other.py", lit)
    hits = truth_references(tmp_path / "src")
    assert not any(h.endswith("kit.py") for h in hits)
    assert any(h.endswith("other.py") for h in hits)
    _plant(tmp_path, "pets_release/kit.py", "import pets_attacker\n")
    assert any(h.endswith("kit.py") for h in attacker_importers(tmp_path / "src"))
