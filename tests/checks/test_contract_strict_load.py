"""#114 (second occurrence of the class): the checks CLI loads the CONTRACT strictly (``manifest.loads_strict``).

Rule: a contract with a duplicate key at any depth, or NaN/Infinity, is refused as unreadable (exit 2, nothing
runs); plain ``json.load`` kept the last duplicate and ran the gate on a partially parsed contract.

Rows (trigger -> result), seam: ``python -m pets_release.checks`` (real CLI, subprocess):
  duplicate top-level "files" (first empty, last the real contract) -> exit 2 "contract unreadable" (was: exit 0)
  duplicate nested key inside a file spec                            -> exit 2
  NaN in the contract                                                 -> exit 2
  the unplanted contract on the same folder                           -> exit 0 (control)
Synthetic fixture rows only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FIX = ROOT / "tests" / "fixtures" / "refusals"
RAW = (FIX / "contract.json").read_text(encoding="utf-8").strip()


def _cli(*args):
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pets_release.checks", *args],
                          check=False, capture_output=True, text=True, env=env)


def _run(tmp_path, contract_text):
    rel = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", rel)
    c = tmp_path / "contract.json"
    c.write_text(contract_text, encoding="utf-8")
    return _cli("--contract", str(c), "--phase", "gate", "--check", "contract.files", str(rel))


def _nested_dup():
    # duplicate the "columns" key inside the first file spec: first value empty, last value the real one
    i = RAW.index('"columns"')
    return RAW[:i] + '"columns": {}, ' + RAW[i:]


def test_unplanted_contract_runs(tmp_path):
    p = _run(tmp_path, RAW)
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("text", [
    '{"files": {}, ' + RAW[1:],
    _nested_dup(),
    '{"x": NaN, ' + RAW[1:],
], ids=["dup-top", "dup-nested", "nan"])
def test_non_strict_contract_is_refused(tmp_path, text):
    p = _run(tmp_path, text)
    assert p.returncode == 2, p.stdout + p.stderr
    assert "contract unreadable" in p.stderr
    assert p.stdout == ""  # nothing ran
