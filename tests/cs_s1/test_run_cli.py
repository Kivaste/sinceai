"""``pets-release run --scenario CS-S1 --plan hand`` through the real CLI on the synthetic minikit.

Rows (trigger -> result):
  hand plan                          -> exit 0, release + scoring folder, gate pass/not_applicable only
  same release, verify / verify --full -> "VERIFIED (limited)" / "VERIFIED (full)"
  generated minikit turn_id          -> release-scope pseudonym; justification names turn-id-synthetic
  manifest measured.utility          -> CS-U1, CS-U3, CS-U4, CS-U5 (turn_id restored through the row map)
                                        before/after + ungated CS-U5.unmodified (kit score without it)
  producer.person-k / row-k          -> not_applicable (no k target), never not_run
  manifest measured.redaction        -> exact-match, held-out; residual text_recall risks for 6 labels
  export assertions                  -> healthInText present, quasiIdentifiersBelowK absent (no k)
  local spot-check sheet             -> <out>.scoring/spot_check.csv (outside the repo)
  two runs, same key and --created   -> byte-identical release folders
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from cs_kit import build_cs_kit, cs_run_args
from run_helpers import cli

HEX64 = re.compile(r"^[0-9a-f]{64}$")



@pytest.fixture(scope="module")
def cs_run(tmp_path_factory):
    base = tmp_path_factory.mktemp("csrun")
    kit = build_cs_kit(base / "kit")
    out = base / "out" / "rel"
    return kit, out, cli(*cs_run_args(kit, out))


def _gate(out):
    sc = out.parent / f"{out.name}.scoring"
    for name in ("gate_report.json", "refusal_report.json"):
        if (sc / name).is_file():
            rep = json.loads((sc / name).read_text(encoding="utf-8"))
            return rep.get("gate", rep)
    raise AssertionError("no gate report")


def test_gate_passes_with_turn_id_record(cs_run):
    _, out, proc = cs_run
    bad = sorted((r["check"], r["status"]) for r in _gate(out)["records"] if r["status"] not in ("pass", "not_applicable"))
    assert bad == [], proc.stdout
    recs = {r["check"]: r for r in _gate(out)["records"]}
    assert recs["turn-id-synthetic"]["status"] == "pass" and recs["turn-id-synthetic"]["hits"] == 0
    assert recs["producer.person-k"]["status"] == "not_applicable"
    assert recs["producer.row-k"]["status"] == "not_applicable"


def test_measurement_reports_in_scoring_folder(cs_run):
    _, out, _ = cs_run
    sc = out.parent / f"{out.name}.scoring"
    util = json.loads((sc / "utility_report.json").read_text(encoding="utf-8"))
    assert {"CS-U1", "CS-U3", "CS-U4", "CS-U5", "CS-U5.unmodified"} <= set(util)
    red = json.loads((sc / "redaction_report.json").read_text(encoding="utf-8"))
    assert red["status"] == "measured" and red["split"]["held_out_turns"] > 0
    tid = json.loads((sc / "turn_id_assessment.json").read_text(encoding="utf-8"))
    assert tid["status"] == "fail" and "conversationOrder" in tid["hits"]


def test_spot_check_sheet_written_outside_repo(cs_run):
    _, out, _ = cs_run
    sheet = out.parent / f"{out.name}.scoring" / "spot_check.csv"
    assert sheet.is_file()
    assert not str(sheet.resolve()).startswith(str(Path(__file__).resolve().parents[2]))
    assert sheet.read_text(encoding="utf-8-sig").splitlines()[0] == "turn_id,original,redacted,missed,over_redacted"


def test_released_and_both_verify_tiers(cs_run):
    kit, out, proc = cs_run
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert sorted(p.name for p in out.iterdir()) == ["conversations.csv", "privacy_manifest.json", "turns.csv"]
    lim = cli("verify", str(out))
    assert lim.returncode == 0 and lim.stdout.strip().startswith("VERIFIED (limited):"), lim.stdout
    full = cli("verify", "--full", "--kit", str(kit), str(out))
    assert full.returncode == 0 and "VERIFIED (full)" in full.stdout, full.stdout + full.stderr


def test_manifest_turn_id_measurements_and_risks(cs_run):
    _, out, proc = cs_run
    assert proc.returncode == 0
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    j = next(x for x in m["fieldJustifications"] if (x["table"], x["column"]) == ("turns", "turn_id"))
    assert j["rung"] == "id.pseudonym" and "turn-id-synthetic" in j["reason"]
    assert any(g["check"] == "turn-id-synthetic" and g["status"] == "pass" for g in m["gate"]["checks"])
    tasks = {t["task"]: t for t in m["measured"]["utility"]["tasks"]}
    assert {"CS-U1", "CS-U3", "CS-U4", "CS-U5", "CS-U5.unmodified"} <= set(tasks)
    assert all(tasks[t]["before"] is not None for t in tasks)
    assert tasks["CS-U5.unmodified"]["after"] == 0.0  # kit score without the row map
    assert tasks["CS-U5"]["after"] >= 0.8  # gated score through the row map, at or above the floor
    sac = {s["check"]: s for s in m["sacrifices"]}
    assert sac["CS-U5"]["floor"] == 0.8 and sac["CS-U5"]["after"] == tasks["CS-U5"]["after"]
    assert m["measured"]["redaction"]["status"] == "measured" and m["measured"]["redaction"]["mode"] == "exact"
    risks = {r["label"]: r for r in m["residualRisks"] if r["kind"] == "text_recall"}
    assert set(risks) == {"PERSON", "ADDRESS", "LOCATION", "ORG", "DATE", "AGE"}
    assert risks["PERSON"]["rate"]["status"] == "measured"
    assert "healthInText" in m["exportAssertions"] and "quasiIdentifiersBelowK" not in m["exportAssertions"]
    import pandas as pd

    conv = pd.read_csv(out / "conversations.csv", dtype=str, keep_default_na=False, na_filter=False)
    turns = pd.read_csv(out / "turns.csv", dtype=str, keep_default_na=False, na_filter=False)
    assert conv.conversation_id.map(lambda v: bool(HEX64.match(v))).all()
    assert set(turns.conversation_id) == set(conv.conversation_id)


def test_two_runs_byte_identical(cs_run, tmp_path):
    kit, out, proc = cs_run
    assert proc.returncode == 0
    out2 = tmp_path / "rel"
    assert cli(*cs_run_args(kit, out2)).returncode == 0

    def dig(d):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir())}

    assert dig(out) == dig(out2)
