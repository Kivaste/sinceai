"""#114: every reader of the release manifest parses it strictly (one loader, ``manifest.loads_strict``).

Rule: a manifest with a duplicate key at any depth, or a non-finite number (NaN/Infinity), is refused by every
check that reads it; the check never passes on a partially parsed record (plain ``json.loads`` keeps the last
duplicate, so an identifier in a dropped value was never scanned).

Rows (trigger -> result), seam named per test:
  [checks CLI] top-level duplicate key, first value carries a card, last value clean
      release.manifest-values                          -> fail (manifestUnparseable), exit 1 (was: pass, exit 0)
  [checks CLI] nested duplicate key, same plant        -> fail, exit 1
  [checks CLI] NaN / Infinity in the manifest          -> fail, exit 1
  [checks CLI] release.file-digests, duplicate "bindings" (last value correct) -> not pass, exit 1 (was: pass)
  [checks CLI] release.file-digests with the correct bindings once  -> pass (control)
  [checks CLI] a clean manifest-values run on the same folder   -> pass (control: the plant, not the folder, refuses)
  [runner] producer.original-values / unkeyed-hashes / key-material on a duplicate-key manifest -> error
  (the verify CLI path: tests/verify/test_manifest_strict_load_verify.py)
All values are synthetic and hand-made; the card is the published test number.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FIX = ROOT / "tests" / "fixtures" / "refusals"
CONTRACT = FIX / "contract.json"
MANIFEST = "privacy_manifest.json"
CARD = "4111111111111111"
SCAN = "release.manifest-values"
DIGESTS = "release.file-digests"


def _cli(*args):
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pets_release.checks", *args],
                          check=False, capture_output=True, text=True, env=env)


def _release(tmp_path, manifest_text):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    (out / MANIFEST).write_text(manifest_text, encoding="utf-8")
    return out


def _record(proc, name):
    summary = json.loads(proc.stdout)
    return next(r for r in summary["records"] if r["check"] == name)


DUP_TOP = '{"note": "call back card ' + CARD + '", "note": "ok"}'
DUP_NESTED = '{"a": {"note": "call back card ' + CARD + '", "note": "ok"}}'


@pytest.mark.parametrize("text", [DUP_TOP, DUP_NESTED, '{"x": NaN}', '{"x": [Infinity]}', '{"x": -Infinity}'],
                         ids=["dup-top", "dup-nested", "nan", "inf", "neg-inf"])
def test_manifest_values_refuses_a_non_strict_manifest(tmp_path, text):
    rel = _release(tmp_path, text)
    p = _cli("--contract", str(CONTRACT), "--phase", "verify", "--check", SCAN, str(rel))
    rec = _record(p, SCAN)
    assert (rec["status"], rec["hits"], p.returncode) == ("fail", 1, 1), p.stdout
    assert CARD not in p.stdout + p.stderr


def test_manifest_values_passes_the_clean_control(tmp_path):
    rel = _release(tmp_path, '{"note": "ok"}')
    p = _cli("--contract", str(CONTRACT), "--phase", "verify", "--check", SCAN, str(rel))
    assert (_record(p, SCAN)["status"], p.returncode) == ("pass", 0), p.stdout


def _bound_files():
    import hashlib

    src = FIX / "valid" / "release"
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(src.glob("*.csv"))}


def test_file_digests_control_passes_with_correct_bindings(tmp_path):
    rel = _release(tmp_path, json.dumps({"bindings": {"files": _bound_files()}}))
    p = _cli("--contract", str(CONTRACT), "--phase", "verify", "--check", DIGESTS, str(rel))
    assert (_record(p, DIGESTS)["status"], p.returncode) == ("pass", 0), p.stdout


def test_file_digests_refuses_a_duplicate_key_manifest(tmp_path):
    # first value binds nothing, last value binds every file correctly: last-wins parsing would pass
    good = json.dumps({"files": _bound_files()})
    rel = _release(tmp_path, '{"bindings": {"files": {}}, "bindings": ' + good + '}')
    p = _cli("--contract", str(CONTRACT), "--phase", "verify", "--check", DIGESTS, str(rel))
    assert _record(p, DIGESTS)["status"] != "pass" and p.returncode == 1, p.stdout


@pytest.mark.parametrize("name", ["producer.original-values", "producer.unkeyed-hashes", "producer.key-material"])
def test_producer_value_checks_refuse_a_duplicate_key_manifest(tmp_path, name):
    import pandas as pd

    from pets_release.checks import all_checks, run_checks

    rel = tmp_path / "rel"
    rel.mkdir()
    (rel / "ed_visits.csv").write_text("sex,note\nF,ok\nM,\n", encoding="utf-8")
    (rel / MANIFEST).write_text('{"x": "' + CARD + '", "x": "ok"}', encoding="utf-8")
    ctx = {"source": {"ed_visits": pd.DataFrame({"visit_id": ["V1"], "card": [CARD]}, dtype=str)},
           "identifiers": [{"table": "ed_visits", "column": "card"}],
           "keys": ["synthetic-test-key-0123456789-abcdefghij"]}
    chk = {c.name: c for c in all_checks()}[name]
    contract = {"files": {"ed_visits.csv": {"columns": {"sex": {}, "note": {}}}}}
    rec = run_checks(rel, contract, ctx, checks=[chk]).to_dict()["records"][0]
    assert rec["status"] == "error", rec
