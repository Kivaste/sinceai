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


def test_committed_refusals_match_generator(tmp_path, gen):
    gen.generate_refusals(tmp_path / "r")
    assert _tree(tmp_path / "r") == _tree(REFUSALS, REFUSALS_STATIC)


def test_committed_manifest_release_matches_generator(tmp_path, gen):
    gen.generate_manifest(tmp_path / "m")
    assert _tree(tmp_path / "m") == _tree(MANIFEST)


def test_drift_is_detected(tmp_path, gen):
    """The comparison used above fails on a one-byte edit and on a planted extra file."""
    gen.generate_refusals(tmp_path / "r")
    fresh = _tree(tmp_path / "r")
    edited = dict(fresh)
    key = sorted(edited)[0]
    edited[key] = edited[key] + b" "
    assert edited != fresh
    planted = dict(fresh)
    planted["planted/extra.csv"] = b"x\n"
    assert planted != fresh


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
