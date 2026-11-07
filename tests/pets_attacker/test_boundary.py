"""Truth-boundary and import-graph guards.

Seam: AST scan of every Python file under src/. Catches a planted truth
path/segment or a planted pets_attacker import (including importlib).
Misses non-Python files and truth paths built from non-literal pieces.
"""

from __future__ import annotations

from pathlib import Path

from pets_attacker.boundary import attacker_importers, attacker_reads_truth, truth_references

SRC = Path(__file__).resolve().parents[2] / "src"


def _plant(root: Path, rel: str, text: str) -> None:
    p = root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_only_the_attacker_package_references_truth():
    assert attacker_reads_truth(SRC)
    assert truth_references(SRC) == []


def test_planted_truth_reference_is_caught(tmp_path: Path):
    _plant(tmp_path, "pets_release/checks/gate.py", 'PATH = "truth/health__ed_visits.csv"\n')
    _plant(tmp_path, "pets_release/other.py", 'p = root / "truth" / "x.csv"\n')
    _plant(tmp_path, "pets_release/win.py", 'p = "kit\\\\truth\\\\x.csv"\n')
    hits = truth_references(tmp_path / "src")
    assert any(h.endswith("gate.py") for h in hits)
    assert any(h.endswith("other.py") for h in hits)
    assert any(h.endswith("win.py") for h in hits)


def test_truth_inside_attacker_is_allowed(tmp_path: Path):
    _plant(tmp_path, "pets_attacker/truth.py", 'P = "truth/x.csv"\n')
    assert truth_references(tmp_path / "src") == []
    assert attacker_reads_truth(tmp_path / "src")


def test_word_truth_in_prose_is_not_a_reference(tmp_path: Path):
    _plant(tmp_path, "pets_release/doc.py", '"""ground truth is not used here."""\nX = "the truth"\n')
    assert truth_references(tmp_path / "src") == []


def test_minimiser_and_gate_do_not_import_the_attacker():
    assert attacker_importers(SRC) == []


def test_planted_imports_are_caught(tmp_path: Path):
    _plant(tmp_path, "pets_release/minimiser.py", "import pets_attacker\n")
    _plant(tmp_path, "pets_release/gate.py", "from pets_attacker.personas import broker_attack\n")
    _plant(tmp_path, "pets_release/sneak.py", 'import importlib\nimportlib.import_module("pets_attacker")\n')
    _plant(tmp_path, "pets_release/sneak2.py", '__import__("pets_attacker.linkage")\n')
    hits = attacker_importers(tmp_path / "src")
    for name in ("minimiser", "gate", "sneak", "sneak2"):
        assert any(h.endswith(f"{name}.py") for h in hits), name


def test_attacker_importing_itself_is_fine(tmp_path: Path):
    _plant(tmp_path, "pets_attacker/a.py", "from pets_attacker import b\n")
    assert attacker_importers(tmp_path / "src") == []


def test_bom_prefixed_file_is_still_scanned(tmp_path: Path):
    p = tmp_path / "src" / "pets_release" / "bom.py"
    p.parent.mkdir(parents=True)
    p.write_bytes(b'\xef\xbb\xbfimport pets_attacker\nP = "truth/x.csv"\n')
    assert any(h.endswith("bom.py") for h in attacker_importers(tmp_path / "src"))
    assert any(h.endswith("bom.py") for h in truth_references(tmp_path / "src"))


def test_unparseable_file_fails_closed(tmp_path: Path):
    _plant(tmp_path, "pets_release/broken.py", 'import pets_attacker\nP = "truth/x.csv"\ndef (:\n')
    assert any(h.endswith("broken.py") for h in attacker_importers(tmp_path / "src"))
    assert any(h.endswith("broken.py") for h in truth_references(tmp_path / "src"))
