"""Release writer: publish only a gated, fully evidenced, signed release; otherwise refuse and publish nothing.

Rule: ``<out>/`` appears (by one rename) only when the registry's own gate passed, every required export assertion
is backed by a pass record with 0 hits and n >= 1, the manifest validates and the self-scan passes. Failure rows,
trigger -> result:
  planted card in a cell                -> rescan check fails -> refused, no <out>/, value-free refusal report
  producer context absent               -> producer checks not_run -> refused
  caller tries to pass its own checks   -> TypeError (no such argument): the gate is always the registry
  gate records differ from the registry -> refused (gate:registry-mismatch)
  hard crash after the gate             -> no <out>/
  <out>/ or <out>.scoring/ exists       -> WriterError, nothing touched
  unjustified contract column           -> refused
  value copied into manifest text       -> self-scan refuses
  bindings.inputs                       -> digest of every kit table of the scenario's dataset (withheld too)
(assertion status matrix: test_assemble.py)

Producer checks (ticket 11) run for real on a synthetic source context (writer_helpers.producer_context).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from writer_helpers import KIT_TABLES, MASTER, ROOT, make_candidate, make_kit, producer_context

from pets_release.checks import Outcome, all_checks
from pets_release.checks import registry as _registry
from pets_release.checks.registry import Check
from pets_release.kiteval import Lineage
from pets_release.manifest import (
    MANIFEST_FILENAME,
    canonical_bytes,
    compute_signature,
    loads_strict,
    required_assertions,
    validate_manifest_file,
)
from pets_release.pseudonym import manifest_signing_key
from pets_release.writer import WriterError, core, load_lineage, scoring_dir, write_release

PY = sys.executable
PLANTED_CARD = "4111111111111111"


def _env() -> dict:
    env = dict(os.environ)
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TZ="UTC",
               PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(ROOT / "tests" / "writer")]))
    return env


def _all_bytes(folder: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file())


def _released(tmp_path, cand=None, context=None):
    cand = cand or make_candidate()
    kit = make_kit(tmp_path / "kit", cand)
    out = tmp_path / "o" / "rel"
    ctx = producer_context(cand) if context is None else context
    res = write_release(cand, out, MASTER, kit, context=ctx)
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


def test_inputs_bind_every_table_of_the_dataset_including_withheld(tmp_path):
    out, _ = _released(tmp_path)
    m = loads_strict((out / MANIFEST_FILENAME).read_bytes())
    data = tmp_path / "kit" / "data" / "health"
    expect = {t: hashlib.sha256((data / f"{t}.csv").read_bytes()).hexdigest() for t in KIT_TABLES}
    assert m["bindings"]["inputs"] == expect
    assert "clinical_notes" in m["bindings"]["inputs"] and "clinical_notes.csv" not in m["bindings"]["files"]


def test_scenario_unknown_to_kit_is_an_error(tmp_path):
    cand = make_candidate()
    kit = make_kit(tmp_path / "kit", cand)
    (tmp_path / "kit" / "metadata" / "scenarios.json").write_text("[]", encoding="utf-8")
    with pytest.raises(WriterError):
        write_release(cand, tmp_path / "o" / "rel", MASTER, kit, context=producer_context(cand))
    assert not (tmp_path / "o").exists() or list((tmp_path / "o").iterdir()) == []


def test_every_assertion_is_literal_false_and_backed_by_a_clean_gate_record(tmp_path):
    out, _ = _released(tmp_path)
    m = loads_strict((out / MANIFEST_FILENAME).read_bytes())
    assert m["exportAssertions"] == {a: False for a in required_assertions("HEALTH-S1")}
    gate = {c["check"]: c for c in m["gate"]["checks"]}
    assert set(gate) == {c.name for c in all_checks()}
    for ev in m["assertionEvidence"].values():
        assert ev == gate[ev["check"]] and ev["hits"] == 0 and ev["denominator"]["n"] >= 1


def test_not_applicable_check_is_listed_in_gate_but_backs_nothing(tmp_path, monkeypatch):
    all_checks()
    na = Check(name="zz.text-only", version="1.0.0", scope="release", unit="turns",
               run=lambda release, contract, context: Outcome.not_applicable(), applies_to=("text",))
    monkeypatch.setitem(_registry._CHECKS, "zz.text-only", na)  # fixture contract has no text column
    out, res = _released(tmp_path)
    assert res.status == "released", res.reasons
    m = loads_strict((out / MANIFEST_FILENAME).read_bytes())
    entry = {c["check"]: c for c in m["gate"]["checks"]}["zz.text-only"]
    assert entry["status"] == "not_applicable" and entry["denominator"]["n"] == 0
    assert m["bindings"]["checkVersions"]["zz.text-only"] == "1.0.0"
    assert "zz.text-only" not in {e["check"] for e in m["assertionEvidence"].values()}
    assert validate_manifest_file(out) == []


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
        orig = {tuple(r): k for r, k in zip(t.frame.itertuples(index=False, name=None), t.final, strict=True)}
        expect_final = [orig[tuple(r)] for r in body]
        assert lineage[stem] == {"final": expect_final, "suppressed": sorted(t.suppressed)}
        rm = list(csv.DictReader(io.StringIO((sc / f"rowmap_{stem}.csv").read_text(encoding="utf-8"))))
        assert [(r["protected_row"], r["original_record_id"]) for r in rm] == \
            [(str(i), k) for i, k in enumerate(expect_final)]


def test_load_lineage_gives_kiteval_lineage(tmp_path):
    out, _ = _released(tmp_path)
    lin = load_lineage(scoring_dir(out))
    assert set(lin) == {"ed_visits", "lab_results"}
    assert isinstance(lin["ed_visits"], Lineage)
    assert len(lin["ed_visits"].final) == 10 and lin["ed_visits"].suppressed == frozenset({"src-ed_visits-dropped"})


def test_same_inputs_give_byte_identical_release(tmp_path):
    a, _ = _released(tmp_path / "a")
    b, _ = _released(tmp_path / "b")
    assert _all_bytes(a) == _all_bytes(b)
    assert _all_bytes(scoring_dir(a)) == _all_bytes(scoring_dir(b))


def test_no_build_folders_left_behind(tmp_path):
    out, _ = _released(tmp_path)
    assert sorted(p.name for p in out.parent.iterdir()) == ["rel", "rel.scoring"]


# --- the gate is always the registry ----------------------------------------------------------------------------

def test_caller_cannot_supply_checks(tmp_path):
    cand = make_candidate()
    kit = make_kit(tmp_path / "kit", cand)
    passing = [Check(name=c.name, version=c.version, scope=c.scope, unit=c.unit,
                     run=lambda release, contract, context: Outcome(n=1)) for c in all_checks()]
    with pytest.raises(TypeError):
        write_release(cand, tmp_path / "o" / "rel", MASTER, kit, context={}, checks=passing)
    assert not (tmp_path / "o").exists()


def test_gate_records_that_differ_from_the_registry_refuse(tmp_path, monkeypatch):
    real = core.run_checks

    def substituted(*a, **k):  # a gate that silently skipped one check and reported a wrong version
        res = real(*a, **k)
        recs = tuple(r for r in res.records if r.check != "rescan.payment-cards")
        return type(res)(refused=res.refused, records=recs, registry_error=res.registry_error)
    monkeypatch.setattr(core, "run_checks", substituted)
    out, res = _released(tmp_path)
    assert res.status == "refused" and "gate:registry-mismatch" in res.reasons
    assert not out.exists()


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
    assert sorted(p.name for p in out.parent.iterdir()) == ["rel.scoring"]


def test_absent_producer_context_refuses(tmp_path):
    out, res = _released(tmp_path, context={})
    assert res.status == "refused" and not out.exists()
    assert "assertion:quasiIdentifiersBelowK:status:not_run" in res.reasons


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


def _with_unit(cand, value):
    t = cand.tables[1]  # lab_results
    frame = t.frame.copy()
    frame.loc[0, "unit"] = value
    return make_candidate(tables=(cand.tables[0], type(t)(t.name, frame, t.final, t.suppressed)),
                          narrative=cand.narrative)


def test_copied_value_containing_a_schema_name_still_refuses(tmp_path):
    """Masking schema names must not hide a released value that merely contains one (review finding, ticket 23)."""
    value = "xxtriage"  # synthetic cell value (fits the unit form) containing the column name triage
    cand = make_candidate()
    nar = dict(cand.narrative)
    nar["fitFor"] = [{"scenario": "HEALTH-S1", "reason": f"built for {value}"}]
    out, res = _released(tmp_path, _with_unit(make_candidate(narrative=nar), value))
    assert res.status == "refused" and "selfscan:manifest-value" in res.reasons, res.reasons
    assert not out.exists()


def test_value_inside_a_schema_name_only_is_not_a_hit(tmp_path):
    """A released value occurring only inside schema-name text (value "readmit", column "readmit_30d") is permitted."""
    out, res = _released(tmp_path, _with_unit(make_candidate(), "readmit"))
    assert res.status == "released", res.reasons


@pytest.mark.parametrize("existing", ["rel", "rel.scoring"])
def test_existing_output_is_never_overwritten(tmp_path, existing):
    (tmp_path / "o" / existing).mkdir(parents=True)
    (tmp_path / "o" / existing / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(WriterError):
        _released(tmp_path)
    assert sorted(p.name for p in (tmp_path / "o").iterdir()) == [existing]


# --- crash ------------------------------------------------------------------------------------------------------

CRASH = r"""
import os, sys
from pathlib import Path
import pets_release.writer.core as core
from writer_helpers import MASTER, make_candidate, make_kit, producer_context
stage = sys.argv[2]
def boom(*a, **k):
    os._exit(9)
setattr(core, stage, boom)
cand = make_candidate()
kit = make_kit(Path(sys.argv[3]), cand)
core.write_release(cand, Path(sys.argv[1]), MASTER, kit, context=producer_context(cand))
"""


@pytest.mark.parametrize("stage", ["assemble_manifest", "_self_scan", "_rename_release"])
def test_hard_crash_after_gate_leaves_no_release(tmp_path, stage):
    out = tmp_path / "o" / "rel"
    proc = subprocess.run([PY, "-c", CRASH, str(out), stage, str(tmp_path / "kit")], env=_env(),
                          capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert proc.returncode == 9, proc.stderr[-2000:]
    assert not out.exists()


def test_exception_after_gate_leaves_no_release_and_cleans_build(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("injected")
    monkeypatch.setattr(core, "assemble_manifest", boom)
    with pytest.raises(RuntimeError):
        _released(tmp_path)
    assert list((tmp_path / "o").iterdir()) == []


def test_manifest_bytes_are_canonical(tmp_path):
    out, _ = _released(tmp_path)
    raw = (out / MANIFEST_FILENAME).read_bytes()
    assert canonical_bytes(loads_strict(raw)) == raw
