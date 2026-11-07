"""Release writer: publish only a gated, fully evidenced, signed release; otherwise refuse and publish nothing.

Rule: ``<out>/`` appears (by one rename) only when the gate passed, every required export assertion is backed by a
pass record with 0 hits and n >= 1, the manifest validates and the self-scan passes. Failure rows, trigger -> result:
  planted card in a cell             -> rescan check fails -> refused, no <out>/, value-free refusal report
  assertion check unregistered       -> no evidence        -> refused
  assertion check not_run / error    -> refused
  assertion check pass + low hits    -> refused (unit table in test_assemble.py)
  hard crash after the gate          -> no <out>/
  <out>/ or <out>.scoring/ exists    -> WriterError, nothing touched
  unjustified contract column        -> refused
  value copied into manifest text    -> self-scan refuses
  check selection drops a registered check -> WriterError
"""
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from writer_helpers import MASTER, ROOT, checks_with_stubs, make_candidate, stub

from pets_release.checks import Outcome, Violation, all_checks
from pets_release.manifest import (
    MANIFEST_FILENAME,
    canonical_bytes,
    compute_signature,
    loads_strict,
    required_assertions,
    validate_manifest_file,
)
from pets_release.pseudonym import manifest_signing_key
from pets_release.writer import WriterError, scoring_dir, write_release

PY = sys.executable
PLANTED_CARD = "4111111111111111"


def _env() -> dict:
    env = dict(os.environ)
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TZ="UTC",
               PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(ROOT / "tests" / "writer")]))
    return env


def _all_bytes(folder: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file())


def _released(tmp_path, cand=None, **kw):
    out = tmp_path / "rel"
    res = write_release(cand or make_candidate(), out, MASTER, context={}, checks=checks_with_stubs(), **kw)
    return out, res


# --- success path -----------------------------------------------------------------------------------------------

def test_release_contains_only_protected_tables_and_manifest(tmp_path):
    out, res = _released(tmp_path)
    assert res.status == "released", res.reasons
    assert sorted(p.name for p in out.iterdir()) == ["ed_visits.csv", "lab_results.csv", MANIFEST_FILENAME]
    assert all(p.is_file() for p in out.iterdir())


def test_manifest_validates_with_02_cli_and_signature_verifies(tmp_path):
    out, _ = _released(tmp_path)
    proc = subprocess.run([PY, "-m", "pets_release.manifest", "validate", str(out)], env=_env(),
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout
    assert validate_manifest_file(out) == []
    m = loads_strict((out / MANIFEST_FILENAME).read_bytes())
    sk = manifest_signing_key(MASTER)
    assert m["signature"] == {"alg": "HMAC-SHA256", "keyId": sk.key_id(), "value": compute_signature(m, sk)}


def test_every_assertion_is_literal_false_and_backed_by_a_clean_gate_record(tmp_path):
    out, _ = _released(tmp_path)
    m = loads_strict((out / MANIFEST_FILENAME).read_bytes())
    assert m["exportAssertions"] == {a: False for a in required_assertions("HEALTH-S1")}
    gate = {c["check"]: c for c in m["gate"]["checks"]}
    for ev in m["assertionEvidence"].values():
        assert ev == gate[ev["check"]] and ev["hits"] == 0 and ev["denominator"]["n"] >= 1


def test_tables_written_sorted_and_row_maps_match_lineage(tmp_path):
    cand = make_candidate()
    out, _ = _released(tmp_path, cand)
    sc = scoring_dir(out)
    lineage = json.loads((sc / "lineage.json").read_text(encoding="utf-8"))
    for t in cand.tables:
        stem = t.name[:-4]
        rows = list(csv.reader(io.StringIO((out / t.name).read_text(encoding="utf-8"), newline="")))
        body = rows[1:]
        assert rows[0] == list(t.frame.columns) and body == sorted(body)
        # input was reversed: source key of written row i is the reversed index
        orig = {tuple(r): k for r, k in zip(t.frame.itertuples(index=False, name=None), t.final, strict=True)}
        expect_final = [orig[tuple(r)] for r in body]
        assert lineage[stem] == {"final": expect_final, "suppressed": sorted(t.suppressed)}
        rm = list(csv.DictReader(io.StringIO((sc / f"rowmap_{stem}.csv").read_text(encoding="utf-8"))))
        assert [(r["protected_row"], r["original_record_id"]) for r in rm] == \
            [(str(i), k) for i, k in enumerate(expect_final)]


def test_load_lineage_gives_kiteval_shape(tmp_path):
    from pets_release.writer import load_lineage
    out, _ = _released(tmp_path)
    lin = load_lineage(scoring_dir(out))
    assert set(lin) == {"ed_visits", "lab_results"}
    assert len(lin["ed_visits"].final) == 10 and lin["ed_visits"].suppressed == frozenset({"src-ed_visits-dropped"})


def test_same_inputs_give_byte_identical_release(tmp_path):
    a, _ = _released(tmp_path / "a")
    b, _ = _released(tmp_path / "b")
    assert _all_bytes(a) == _all_bytes(b)
    assert _all_bytes(scoring_dir(a)) == _all_bytes(scoring_dir(b))


def test_no_build_folders_left_behind(tmp_path):
    _out, _ = _released(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rel", "rel.scoring"]


# --- refusal ----------------------------------------------------------------------------------------------------

def _plant_card(cand):
    t = cand.tables[1]  # lab_results
    frame = t.frame.copy()
    frame.loc[0, "unit"] = PLANTED_CARD
    return make_candidate(tables=(cand.tables[0], type(t)(t.name, frame, t.final, t.suppressed)))


def test_planted_hit_refuses_publishes_nothing_and_report_is_value_free(tmp_path):
    out, res = _released(tmp_path, _plant_card(make_candidate()))
    assert res.status == "refused"
    assert not out.exists()
    sc = scoring_dir(out)
    report = loads_strict((sc / "refusal_report.json").read_bytes())
    assert report["status"] == "refused" and "gate:refused" in report["reasons"]
    assert "gate:check:rescan.payment-cards:status:fail" in report["reasons"]
    assert "assertion:paymentCards:status:fail" in report["reasons"]
    assert report["reasons"] == list(res.reasons)
    assert PLANTED_CARD.encode() not in _all_bytes(sc)
    assert sorted(p.name for p in sc.iterdir()) == ["refusal_report.json"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rel.scoring"]


@pytest.mark.parametrize("outcome,reason", [
    (Outcome.not_run(), "status:not_run"),
    (Outcome(n=0), "status:error"),
    (Outcome(n=5, violations=(Violation("producer.person-k", "kBelow", "high", "ed_visits.csv", None, 1),)),
     "status:fail"),
])
def test_assertion_check_not_clean_refuses(tmp_path, outcome, reason):
    checks = checks_with_stubs(replace={"producer.person-k": stub("producer.person-k", status_outcome=outcome)})
    out = tmp_path / "rel"
    res = write_release(make_candidate(), out, MASTER, context={}, checks=checks)
    assert res.status == "refused" and not out.exists()
    assert f"assertion:quasiIdentifiersBelowK:{reason}" in res.reasons


def test_missing_assertion_check_refuses(tmp_path):
    checks = [c for c in checks_with_stubs() if c.name != "producer.person-k"]
    out = tmp_path / "rel"
    if "producer.person-k" in {c.name for c in all_checks()}:
        pytest.skip("check registered; covered by the selection rule")
    res = write_release(make_candidate(), out, MASTER, context={}, checks=checks)
    assert res.status == "refused" and "assertion:quasiIdentifiersBelowK:missing" in res.reasons
    assert not out.exists()


def test_production_registry_refuses_when_producer_context_absent(tmp_path):
    """Real registry, no producer context: anything less than full evidence refuses (never a partial manifest)."""
    out = tmp_path / "rel"
    res = write_release(make_candidate(), out, MASTER, context={})
    assert res.status == "refused" and not out.exists()
    assert any(r.startswith("assertion:quasiIdentifiersBelowK:") for r in res.reasons)


def test_unjustified_contract_column_refuses(tmp_path):
    cand = make_candidate()
    nar = dict(cand.narrative)
    nar["fieldJustifications"] = [f for f in nar["fieldJustifications"] if f["outputColumn"] != "triage"]
    out, res = _released(tmp_path, make_candidate(narrative=nar))
    assert res.status == "refused" and "justification:ed_visits.triage:missing" in res.reasons
    assert not out.exists()


def test_value_copied_into_manifest_text_refuses(tmp_path):
    cand = make_candidate()
    value = "Municipality-A"  # a released synthetic cell value
    nar = dict(cand.narrative)
    nar["fitFor"] = [{"scenario": "HEALTH-S1", "reason": f"built for {value}"}]
    out, res = _released(tmp_path, make_candidate(narrative=nar))
    assert res.status == "refused" and "selfscan:manifest-value" in res.reasons
    assert value.encode() not in _all_bytes(scoring_dir(out))


def test_check_selection_must_cover_the_registry(tmp_path):
    checks = [c for c in checks_with_stubs() if c.name != "rescan.payment-cards"]
    with pytest.raises(WriterError):
        write_release(make_candidate(), tmp_path / "rel", MASTER, context={}, checks=checks)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("existing", ["rel", "rel.scoring"])
def test_existing_output_is_never_overwritten(tmp_path, existing):
    (tmp_path / existing).mkdir()
    (tmp_path / existing / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(WriterError):
        _released(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [existing]


# --- crash ------------------------------------------------------------------------------------------------------

CRASH = r"""
import os, sys
from pathlib import Path
import pets_release.writer.core as core
from writer_helpers import MASTER, checks_with_stubs, make_candidate
stage = sys.argv[2]
def boom(*a, **k):
    os._exit(9)
setattr(core, stage, boom)
core.write_release(make_candidate(), Path(sys.argv[1]), MASTER, context={}, checks=checks_with_stubs())
"""


@pytest.mark.parametrize("stage", ["assemble_manifest", "_self_scan", "_rename_release"])
def test_hard_crash_after_gate_leaves_no_release(tmp_path, stage):
    out = tmp_path / "rel"
    proc = subprocess.run([PY, "-c", CRASH, str(out), stage], env=_env(), capture_output=True, text=True,
                          cwd=str(ROOT), check=False)
    assert proc.returncode == 9, proc.stderr[-2000:]
    assert not out.exists()


def test_exception_after_gate_leaves_no_release_and_cleans_build(tmp_path, monkeypatch):
    from pets_release.writer import core

    def boom(*a, **k):
        raise RuntimeError("injected")
    monkeypatch.setattr(core, "assemble_manifest", boom)
    with pytest.raises(RuntimeError):
        _released(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_manifest_bytes_are_canonical(tmp_path):
    out, _ = _released(tmp_path)
    raw = (out / MANIFEST_FILENAME).read_bytes()
    assert canonical_bytes(loads_strict(raw)) == raw
