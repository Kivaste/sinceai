"""Seams for the refusal and manifest fixtures (follow-up #78).

1. generate_refusals / generate_manifest write the fixture trees from hand-made synthetic values.
   Catches a missing generator. Misses whether the gate still refuses each case (the consumer tests do that).
2. The committed trees equal a fresh run, file set and bytes.
   Catches hand-edits, planted extra files and stale files. Misses drift in a file the generator does not own.
3. Two runs are byte-identical, and the real CLI writes the same bytes as the import.
   Catches clock/order input and a CLI that diverges from the functions.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gen_fixtures.py"
REFUSALS = ROOT / "tests" / "fixtures" / "refusals"
MANIFEST = ROOT / "tests" / "fixtures" / "manifest" / "release"
# Hand-written docs / attributes that live beside generated files and are not generator output.
REFUSALS_STATIC = {".gitattributes", "README.md"}


def _load():
    spec = importlib.util.spec_from_file_location("gen_fixtures", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen():
    return _load()


def _tree(folder: Path, skip: set[str] = frozenset()) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.relative_to(folder).as_posix() not in skip
    }


def test_committed_refusals_match_generator(gen):
    assert gen.check_refusals(REFUSALS) == []


def test_committed_manifest_release_matches_generator(gen):
    assert gen.check_manifest(MANIFEST) == []


@pytest.mark.parametrize("which", ["refusals", "manifest"])
def test_guard_accepts_a_clean_copy(tmp_path, gen, which):
    guard, make = _guard(gen, which)
    make(tmp_path / "t")
    assert guard(tmp_path / "t") == []


@pytest.mark.parametrize("which", ["refusals", "manifest"])
def test_guard_rejects_byte_drift(tmp_path, gen, which):
    guard, make = _guard(gen, which)
    make(tmp_path / "t")
    victim = sorted(p for p in (tmp_path / "t").rglob("*") if p.is_file() and p.suffix in {".csv", ".json"})[0]
    victim.write_bytes(victim.read_bytes() + b" ")
    problems = guard(tmp_path / "t")
    assert problems == [f"changed: {victim.relative_to(tmp_path / 't').as_posix()}"]


@pytest.mark.parametrize("which", ["refusals", "manifest"])
def test_guard_rejects_a_planted_extra_file(tmp_path, gen, which):
    guard, make = _guard(gen, which)
    make(tmp_path / "t")
    (tmp_path / "t" / "planted").mkdir()
    (tmp_path / "t" / "planted" / "extra.csv").write_bytes(b"x\n")
    assert guard(tmp_path / "t") == ["extra: planted/extra.csv"]


@pytest.mark.parametrize("which", ["refusals", "manifest"])
def test_guard_rejects_a_deleted_file_and_a_missing_folder(tmp_path, gen, which):
    guard, make = _guard(gen, which)
    make(tmp_path / "t")
    victim = sorted(p for p in (tmp_path / "t").rglob("*.csv"))[0]
    victim.unlink()
    assert guard(tmp_path / "t") == [f"missing: {victim.relative_to(tmp_path / 't').as_posix()}"]
    assert guard(tmp_path / "absent") != []


def test_refusals_static_files_are_tolerated_but_nothing_else(tmp_path, gen):
    gen.generate_refusals(tmp_path / "t")
    (tmp_path / "t" / "README.md").write_text("doc", encoding="utf-8")
    (tmp_path / "t" / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    assert gen.check_refusals(tmp_path / "t") == []
    (tmp_path / "t" / "NOTES.md").write_text("x", encoding="utf-8")
    assert gen.check_refusals(tmp_path / "t") == ["extra: NOTES.md"]


def test_check_cli_passes_on_the_committed_tree():
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC"}
    out = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stdout + out.stderr


def _guard(gen, which):
    return (gen.check_refusals, gen.generate_refusals) if which == "refusals" else (
        gen.check_manifest, gen.generate_manifest)


def test_refusals_two_runs_are_byte_identical(tmp_path, gen):
    gen.generate_refusals(tmp_path / "a")
    gen.generate_refusals(tmp_path / "b")
    assert _tree(tmp_path / "a") == _tree(tmp_path / "b")


def test_manifest_two_runs_are_byte_identical(tmp_path, gen):
    gen.generate_manifest(tmp_path / "a")
    gen.generate_manifest(tmp_path / "b")
    assert _tree(tmp_path / "a") == _tree(tmp_path / "b")


def test_cli_writes_the_same_bytes(tmp_path, gen):
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC"}
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path / "kit"),
         "--refusals-out", str(tmp_path / "r"), "--manifest-out", str(tmp_path / "m")],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    assert _tree(tmp_path / "r") == _tree(REFUSALS, REFUSALS_STATIC)
    assert _tree(tmp_path / "m") == _tree(MANIFEST)


def test_refusal_cases_keep_their_names(tmp_path, gen):
    gen.generate_refusals(tmp_path / "r")
    cases = {p.name for p in (tmp_path / "r").iterdir() if p.is_dir()}
    assert cases == {
        "valid", "card_in_cell", "empty_table", "extra_column", "hex64_outside_token",
        "raw_birth_date_in_band", "renamed_identifier_column", "row_map_column",
    }
    assert (tmp_path / "r" / "contract.json").is_file()
