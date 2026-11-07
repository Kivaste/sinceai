"""Producer checks are discovered by ticket 04's registry and run through its runner and CLI."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import pets_release.checks as checks_pkg
from pets_release.checks import all_checks, run_checks
from pets_release.run.context import person_normaliser

RECORD_KEYS = {"check", "version", "scope", "status", "denominator", "hits", "violations"}
VIOLATION_KEYS = {"check", "label", "severity", "file", "column", "count", "locations"}
OURS = {
    "producer.person-k": ("producer", "persons"),
    "producer.row-k": ("release", "rows"),
    "producer.original-values": ("producer", "cells"),
    "producer.unkeyed-hashes": ("producer", "cells"),
    "producer.key-material": ("producer", "cells"),
}
KEY = "synthetic-test-key-0123456789-abcdefghij"


def _ours():
    return [c for c in all_checks() if c.name in OURS]


def _ctx(h):
    visits = [f"V{i}" for i in range(6)]
    return {
        "k": 5,
        "source": {"ed_visits": h.frame({"visit_id": visits, "patient_hetu": [f"P{i}0000-00{i}" for i in range(6)]})},
        "rowmaps": {"ed_visits": h.rowmap(visits)},
        "record_keys": {"ed_visits": "visit_id"},
        "person": {"table": "ed_visits", "column": "patient_hetu", "normalise": person_normaliser()},
        "joins": [],
        "identifiers": [{"table": "ed_visits", "column": "patient_hetu"}],
        "keys": [KEY],
    }


def _release(h, name):
    digest = hashlib.sha256(b"P10000-001").hexdigest()
    key_b64 = base64.b64encode(KEY.encode()).decode()
    return h.release(
        {"ed_visits": {"sex": ["F"] * 5 + ["M"], "note": ["P00000-000", digest, key_b64, "", "", ""]}},
        name=name,
    )


CONTRACT = {"k": 5, "files": {}, "qi": [{"table": "ed_visits", "column": "sex", "derived_from": "ed_visits.sex"}], "tokens": []}


def _records(rel, ctx):
    return {r["check"]: r for r in run_checks(rel, CONTRACT, ctx, checks=_ours()).to_dict()["records"]}


def test_registry_discovers_every_producer_check_with_pinned_names():
    found = {c.name: (c.scope, c.unit, c.version) for c in all_checks() if c.name.startswith("producer.")}
    assert found == {n: (s, u, "1.0.0") for n, (s, u) in OURS.items()}


def test_every_check_refuses_its_planted_hit_through_the_runner_deterministically(h):
    a = _records(_release(h, "a"), _ctx(h))
    b = _records(_release(h, "b"), _ctx(h))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert set(a) == set(OURS)
    for name, rec in a.items():
        assert set(rec) == RECORD_KEYS
        assert rec["status"] == "fail", name
        assert rec["hits"] == sum(v["count"] for v in rec["violations"]) > 0
        assert rec["denominator"]["n"] > 0
        for v in rec["violations"]:
            assert set(v) == VIOLATION_KEYS
            assert all(isinstance(x, int) for x in v["locations"])
    assert run_checks(_release(h, "c"), CONTRACT, _ctx(h), checks=_ours()).refused


def test_planted_pass_file_does_not_turn_a_fail_into_a_pass(h):
    rel = _release(h, "planted")
    before = _records(rel, _ctx(h))
    for name in OURS:
        (rel / f"{name}.pass").write_text(json.dumps({"check": name, "status": "pass"}), encoding="utf-8")
    (rel / "gate_pass.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    after = _records(rel, _ctx(h))
    for name in OURS:
        assert before[name]["status"] == after[name]["status"] == "fail"
        assert after[name]["hits"] >= before[name]["hits"]


def test_real_cli_never_passes_producer_checks_without_source_or_key(h, tmp_path):
    rel = _release(h, "cli")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(CONTRACT), encoding="utf-8")
    src = Path(checks_pkg.__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(src), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TZ="UTC")
    proc = subprocess.run(
        [sys.executable, "-m", "pets_release.checks", "--contract", str(contract), "--phase", "gate", str(rel)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert proc.returncode == 1, proc.stderr[-500:]
    summary = json.loads(proc.stdout)
    recs = {r["check"]: r for r in summary["records"]}
    assert summary["refused"] is True
    for name, (scope, _) in OURS.items():
        assert recs[name]["scope"] == scope
        if name == "producer.row-k":  # release scope: k from the contract, runs on the release alone
            assert recs[name]["status"] == "fail"
        else:
            assert recs[name]["status"] == "not_run", name  # CLI supplies no source or key
    assert KEY not in proc.stdout and "P00000-000" not in proc.stdout


@pytest.mark.parametrize("name", sorted(OURS))
def test_missing_release_folder_is_an_error(h, name):
    (chk,) = [c for c in _ours() if c.name == name]
    rec = run_checks(h.release({}).parent / "absent", CONTRACT, _ctx(h), checks=[chk]).to_dict()["records"][0]
    assert rec["status"] == "error"
