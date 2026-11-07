"""#106 (decision D33) at the CLI seam: the detector's QI classification binds contract.qi and producer person-k.
Synthetic minikit rows only.

Rule 1: a released column that the detector classifies as a quasi-identifier (on its released values, or through
its source column) and that is missing from ``contract.qi`` makes ``producer.person-k`` refuse. The classification
of released values never reads declared provenance, so a column whose declared source is wrong cannot escape it.

Rule 2 (D33, branch A): ``lab_results.test_name`` is a QI. Its ladder is full test name -> "CRP vs other" ->
withheld; the hand plan holds the "CRP vs other" rung (only H-U7 needs lab tests, and it selects CRP by
``test_code``); the search may go coarser. The manifest records the branch taken as a residual risk.

Failure rows (trigger -> wrong result before #106):
  R1 kit copy whose lab_results.unit holds a sex vocabulary (a detector QI, not a policy QI), hand plan
       -> run exits 0 and publishes; want exit 1, no manifest, gate names producer.person-k as error
  R2 real hand-plan release, released lab_results.unit overwritten with a sex vocabulary, rebound and re-signed
       -> verify --full exits 0; want exit 1 naming producer.person-k
  R3 hand plan -> test_name released in full and absent from contract.qi; want contract.qi to list it, its
       column at rung lab.crp_other with form ^(?:CRP|other)$, CRP exactly on the P-CRP rows; both tiers exit 0
  R4 hand plan -> no residual risk records the D33 branch; want residualRisks entry lab-test-name-qi
"""
from __future__ import annotations

import json

import pandas as pd
from run_helpers import build_kit, cli, coarse_qis, run_args
from test_verify_assertion_rerun import MANIFEST, copy_release, resign

SEX = ("F", "M")  # synthetic sex vocabulary


def _sex_unit(folder):
    coarse_qis(folder)
    p = folder / "lab_results.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    df["unit"] = [SEX[i % 2] for i in range(len(df))]
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")


def _manifest(rel):
    return json.loads((rel / MANIFEST).read_text(encoding="utf-8"))


def _gate(rel):
    return json.loads((rel.parent / (rel.name + ".scoring") / "gate_report.json").read_text(encoding="utf-8"))


def test_run_refuses_released_detector_qi_missing_from_contract_qi(tmp_path):
    kit = build_kit(tmp_path / "kit", _sex_unit)
    rel = tmp_path / "out" / "rel"
    proc = cli(*run_args(kit, rel))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "REFUSED" in proc.stdout
    assert "check producer.person-k: error" in proc.stdout, proc.stdout
    assert not (rel / MANIFEST).exists()


def test_full_verify_fails_on_released_detector_qi_missing_from_contract_qi(released, tmp_path):
    kit, rel = copy_release(released, tmp_path)
    p = rel / "lab_results.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    assert "unit" in df.columns and not any(q["column"] == "unit" for q in _manifest(rel)["contract"]["qi"])
    df["unit"] = [SEX[i % 2] for i in range(len(df))]
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
    resign(rel)
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 1, full.stdout + full.stderr
    assert "producer.person-k" in full.stdout, full.stdout
    assert "VERIFIED" not in full.stdout.replace("VERIFY FAILED", "")


def test_unmodified_release_still_verifies(released, tmp_path):
    kit, rel = copy_release(released, tmp_path)
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 0, full.stdout + full.stderr


def test_test_name_is_a_qi_at_the_crp_vs_other_rung(released, tmp_path):
    kit, rel = copy_release(released, tmp_path)
    m = _manifest(rel)
    qi = {(q["table"], q["column"]): q for q in m["contract"]["qi"]}
    assert ("lab_results", "test_name") in qi, sorted(qi)
    assert qi[("lab_results", "test_name")]["derived_from"] == "join_ed_visits_visit_id"
    col = m["contract"]["files"]["lab_results.csv"]["columns"]["test_name"]
    assert col["params"]["rung"] == "lab.crp_other"
    assert col["form"] == "^(?:CRP|other)$"
    df = pd.read_csv(rel / "lab_results.csv", dtype=str, keep_default_na=False, na_filter=False)
    assert set(df["test_name"]) <= {"CRP", "other", ""}
    assert ((df["test_name"] == "CRP") == (df["test_code"] == "P-CRP")).all()
    assert (df["test_name"] == "CRP").any() and (df["test_name"] == "other").any()
    inv = {(r["table"], r["column"]): r for r in m["inventory"]}
    assert inv[("lab_results", "test_name")]["role"] == "quasi_identifier"
    assert cli("verify", str(rel)).returncode == 0
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 0, full.stdout + full.stderr


def test_manifest_records_the_d33_branch(released, tmp_path):
    _, rel = copy_release(released, tmp_path)
    risks = {r["risk"]: r for r in _manifest(rel)["residualRisks"]}
    assert "lab-test-name-qi" in risks, sorted(risks)
    text = risks["lab-test-name-qi"]["description"]
    assert "D33" in text and "test_code" in text
