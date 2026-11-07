"""Every producer-submodule check emits the pinned, closed CheckRecord shape."""

from __future__ import annotations

import base64
import hashlib
import json

import pytest

from pets_release.checks.producer import CHECKS

RECORD_KEYS = {"check", "version", "scope", "status", "denominator", "hits", "violations"}
VIOLATION_KEYS = {"check", "label", "severity", "file", "column", "count", "locations"}


def _ctx(h):
    visits = [f"V{i}" for i in range(6)]
    return {
        "k": 5,
        "source": {"ed_visits": h.frame({"visit_id": visits, "patient_hetu": [f"P{i}0000-00{i}" for i in range(6)]})},
        "rowmaps": {"ed_visits": h.rowmap(visits)},
        "record_keys": {"ed_visits": "visit_id"},
        "person": {"table": "ed_visits", "column": "patient_hetu"},
        "joins": [],
        "identifiers": [{"table": "ed_visits", "column": "patient_hetu"}],
        "keys": ["synthetic-test-key-0123456789-abcdefghij"],
    }


def _release(h, name):
    digest = hashlib.sha256(b"P10000-001").hexdigest()
    key_b64 = base64.b64encode(b"synthetic-test-key-0123456789-abcdefghij").decode()
    return h.release(
        {"ed_visits": {"sex": ["F"] * 5 + ["M"], "note": ["P00000-000", digest, key_b64, "", "", ""]}},
        name=name,
    )


CONTRACT = {"files": {}, "qi": [{"table": "ed_visits", "column": "sex", "derived_from": "ed_visits.sex"}], "tokens": []}


def test_check_names_are_unique_and_scoped():
    names = [c.name for c in CHECKS]
    assert len(names) == len(set(names))
    assert {c.name: c.scope for c in CHECKS} == {
        "person_k": "producer",
        "row_k": "release",
        "original_values": "producer",
        "reversible_hashes": "producer",
        "key_material": "producer",
    }


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.name)
def test_record_shape_is_closed_and_deterministic(h, check):
    a = check.run(_release(h, "a"), CONTRACT, _ctx(h))
    b = check.run(_release(h, "b"), CONTRACT, _ctx(h))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert set(a) == RECORD_KEYS
    assert (a["check"], a["version"], a["scope"]) == (check.name, check.version, check.scope)
    assert set(a["denominator"]) == {"unit", "n"} and a["denominator"]["n"] > 0
    assert a["status"] == "fail"  # every check has a planted hit in this release
    for v in a["violations"]:
        assert set(v) == VIOLATION_KEYS
        assert all(isinstance(x, int) for x in v["locations"])


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.name)
def test_planted_pass_file_does_not_turn_a_fail_into_a_pass(h, check):
    rel = _release(h, "planted")
    before = check.run(rel, CONTRACT, _ctx(h))
    for name in (f"{check.name}.pass", "gate_pass.json", "check_results.json"):
        (rel / name).write_text(json.dumps({"check": check.name, "status": "pass"}), encoding="utf-8")
    after = check.run(rel, CONTRACT, _ctx(h))
    assert before["status"] == "fail"
    assert after["status"] == "fail"
    assert after["hits"] >= before["hits"]
