"""The validator CLI, run as a real subprocess on the committed fixture and on mutated copies."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pets_release.manifest import MANIFEST_FILENAME, canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "tests" / "fixtures" / "manifest" / "release"


def run_cli(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pets_release.manifest", *map(str, args)], env=env,
                          capture_output=True, text=True, check=False)


def fixture_obj():
    return json.loads((RELEASE / MANIFEST_FILENAME).read_bytes())


def test_fixture_manifest_file_validates():
    r = run_cli("validate", RELEASE / MANIFEST_FILENAME)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "VALID"


def test_release_dir_validates():
    assert run_cli("validate", RELEASE).returncode == 0


def _set_true(m):
    m["exportAssertions"]["nationalIds"] = True


def _unknown_key(m):
    m["exportAssertions"]["directIdentifiers"] = False


def _missing(m):
    del m["exportAssertions"]["paymentCards"]


@pytest.mark.parametrize("mutate,code", [
    (_set_true, "$.exportAssertions.nationalIds: const"),
    (_unknown_key, "$.exportAssertions: additionalProperties"),
    (_missing, "$.exportAssertions: required"),
])
def test_mutated_copies_fail_with_exit_1(tmp_path, mutate, code):
    m = fixture_obj()
    mutate(m)
    p = tmp_path / MANIFEST_FILENAME
    p.write_bytes(canonical_bytes(m))
    r = run_cli("validate", p)
    assert r.returncode == 1
    assert r.stdout.startswith("INVALID")
    assert code in r.stdout


def test_non_canonical_bytes_fail(tmp_path):
    p = tmp_path / MANIFEST_FILENAME
    p.write_text(json.dumps(fixture_obj(), indent=2), encoding="utf-8")
    r = run_cli("validate", p)
    assert r.returncode == 1 and "$: not-canonical" in r.stdout


def test_duplicate_key_fails(tmp_path):
    raw = (RELEASE / MANIFEST_FILENAME).read_bytes()
    p = tmp_path / MANIFEST_FILENAME
    p.write_bytes(b'{"schemaVersion":"1",' + raw[1:])
    r = run_cli("validate", p)
    assert r.returncode == 1 and "$: not-json" in r.stdout


def test_missing_path_is_exit_2(tmp_path):
    assert run_cli("validate", tmp_path / "nope.json").returncode == 2


def test_empty_release_dir_is_exit_2(tmp_path):
    assert run_cli("validate", tmp_path).returncode == 2


@pytest.mark.parametrize("args", [(), ("validate",), ("check", "x"), ("validate", "a", "b")])
def test_usage_error_is_exit_2(args):
    assert run_cli(*args).returncode == 2
