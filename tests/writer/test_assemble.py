"""Evidence decision: an assertion is emitted (as literal false) only from a pass record with 0 hits and n >= 1.

Records come from 04's real runner over a real folder (no hand-built CheckRecords), so the statuses are the
runner's own. The runner's own ``checks=`` argument is used here to produce each status; the writer has no
such argument (it always runs exactly the registry).
"""
from __future__ import annotations

import pytest

from pets_release.checks import Outcome, Violation, all_checks, run_checks
from pets_release.checks.registry import Check
from pets_release.manifest import ASSERTION_EVIDENCE, required_assertions
from pets_release.writer.assemble import evidence_for

SCEN = "HEALTH-S1"


def stub(name, outcome, unit=None, applies_to=()):
    ev = {e["check"]: e for e in ASSERTION_EVIDENCE.values()}[name]
    return Check(name=name, version="1.0.0", scope=ev["scope"], unit=unit or ev["unit"],
                 run=lambda release, contract, context: outcome, applies_to=tuple(applies_to))


def _records(tmp_path, replace=None):
    d = tmp_path / "r"
    d.mkdir()
    (d / "t.csv").write_text("a\n1\n", encoding="utf-8")
    contract = {"files": {"t.csv": {"required": ["a"], "columns": {"a": {"form": "integer", "params": {}}}}},
                "qi": [], "tokens": []}
    checks = {c.name: c for c in all_checks()}
    for name, c in list(checks.items()):  # producer checks need source context this toy folder lacks
        if name.startswith("producer."):
            checks[name] = Check(name=name, version=c.version, scope=c.scope, unit=c.unit,
                                 run=lambda release, contract, context: Outcome(n=3))
    checks.update(replace or {})
    return run_checks(d, contract, {"phase": "gate"}, checks=list(checks.values())).records


def test_clean_records_give_all_false_assertions(tmp_path):
    assertions, evidence, reasons = evidence_for(_records(tmp_path), SCEN)
    assert reasons == []
    assert assertions == {a: False for a in required_assertions(SCEN)}
    assert all(v is False for v in assertions.values())
    assert set(evidence) == set(assertions)


@pytest.mark.parametrize("outcome,reason", [
    (Outcome(n=4, violations=(Violation("producer.person-k", "kBelow", "low", "t.csv", None, 2),)), "hits"),
    (Outcome(n=4, violations=(Violation("producer.person-k", "kBelow", "high", "t.csv", None, 2),)), "status:fail"),
    (Outcome.not_run(), "status:not_run"),
    (Outcome(n=0), "status:error"),
])
def test_unclean_record_withholds_every_assertion(tmp_path, outcome, reason):
    recs = _records(tmp_path, {"producer.person-k": stub("producer.person-k", outcome)})
    assertions, evidence, reasons = evidence_for(recs, SCEN)
    assert assertions is None and evidence is None
    assert f"assertion:quasiIdentifiersBelowK:{reason}" in reasons


def test_scope_or_unit_mismatch_refuses(tmp_path):
    recs = _records(tmp_path, {"producer.person-k": stub("producer.person-k", Outcome(n=3), unit="rows")})
    assertions, _, reasons = evidence_for(recs, SCEN)
    assert assertions is None and "assertion:quasiIdentifiersBelowK:shape" in reasons


def test_not_applicable_status_never_backs_an_assertion(tmp_path):
    na = stub("rescan.emails", Outcome.not_applicable(), applies_to=("text",))
    recs = _records(tmp_path, {"rescan.emails": na})
    assert {r.check: r.status for r in recs}["rescan.emails"] == "not_applicable"
    assertions, _, reasons = evidence_for(recs, SCEN)
    assert assertions is None and "assertion:emails:status:not_applicable" in reasons


def test_missing_record_refuses(tmp_path):
    recs = tuple(r for r in _records(tmp_path) if r.check != "rescan.emails")
    assertions, _, reasons = evidence_for(recs, SCEN)
    assert assertions is None and "assertion:emails:missing" in reasons
