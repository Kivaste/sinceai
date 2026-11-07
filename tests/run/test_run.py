"""`pets-release run` on the synthetic minikit, through the real CLI and the production checks.

Rows (trigger -> result):
  hand plan on a kit where k is reachable          -> exit 0, release + scoring folder, gate all pass
  same release, recipient verify                   -> exit 0, "VERIFIED (limited)"
  same release, verify --full with kit + key       -> exit 0, "VERIFIED (full)" (producer context rebuilt)
  verify --full with another key                   -> exit 1
  visit pseudonyms in ed_visits and lab_results    -> identical tokens (every lab visit token is a visit token)
  below-k persons                                   -> suppressed, share <= max_share, reported; person-k 0 below k
  below-k share above max_share (raw minikit)       -> exit 1, no release folder, refusal report
  card number planted in a released cell            -> exit 1 via the gate (rescan.payment-cards), no release
  planted row map in the scoring folder             -> ignored by verify --full (row maps rebuilt from tokens)
  two runs, same --created and key                  -> byte-identical release folders
"""
from __future__ import annotations

import hashlib
import json
import re

import pandas as pd
from run_helpers import CREATED, build_kit, cli, coarse_qis, run_args

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _digests(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_release_passes_gate_and_both_verify_tiers(released):
    kit, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RELEASED" in proc.stdout and "gate: " in proc.stdout
    gate = json.loads((out.parent / "rel.scoring" / "gate_report.json").read_text(encoding="utf-8"))
    assert gate["refused"] is False
    assert {r["status"] for r in gate["records"]} <= {"pass", "not_applicable"}
    assert any(r["check"] == "producer.person-k" and r["status"] == "pass" for r in gate["records"])

    lim = cli("verify", str(out))
    assert lim.returncode == 0, lim.stdout + lim.stderr
    assert lim.stdout.strip().startswith("VERIFIED (limited):")

    full = cli("verify", "--full", "--kit", str(kit), str(out))
    assert full.returncode == 0, full.stdout + full.stderr
    assert "VERIFIED (full)" in full.stdout

    wrong = cli("verify", "--full", "--kit", str(kit), str(out),
                extra={"PETS_HMAC_KEY": "another-test-only-key-not-a-secret-00000000000"})
    assert wrong.returncode == 1


def test_visit_pseudonyms_identical_across_tables(released):
    _, out, proc = released
    assert proc.returncode == 0
    ed = pd.read_csv(out / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
    lab = pd.read_csv(out / "lab_results.csv", dtype=str, keep_default_na=False, na_filter=False)
    assert ed["visit_id"].map(lambda v: bool(HEX64.match(v))).all()
    assert len(lab) > 0 and set(lab["visit_id"]) <= set(ed["visit_id"])


def test_suppression_reported_and_person_k_clean(released):
    _, out, proc = released
    assert proc.returncode == 0
    sc = out.parent / "rel.scoring"
    sup = json.loads((sc / "suppression_report.json").read_text(encoding="utf-8"))
    assert 1 <= sup["unitsSuppressed"] and sup["share"] <= sup["maxShare"] == 0.1
    assert sup["personKAfter"]["belowK"] == 0 and sup["personKAfter"]["minK"] >= 5
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert any(p["pet"] == "local_suppression" for p in m["pets"])
    assert m["contract"]["k"] == 5
    lineage = json.loads((sc / "lineage.json").read_text(encoding="utf-8"))
    assert len(lineage["ed_visits"]["suppressed"]) >= 1


def test_share_above_bound_refuses(tmp_path):
    kit = build_kit(tmp_path / "kit")  # raw minikit: the hand plan leaves most persons below k
    out = tmp_path / "out" / "rel"
    proc = cli(*run_args(kit, out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not out.exists()
    rep = json.loads((tmp_path / "out" / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))
    assert rep["reasons"] == ["suppression:share-above-max"]


def test_planted_card_number_refuses_via_cli(tmp_path):
    def plant(folder):
        coarse_qis(folder)
        p = folder / "ed_visits.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df.loc[0, "disposition"] = "4111 1111 1111 1111"  # published test card number
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    kit = build_kit(tmp_path / "kit", plant)
    out = tmp_path / "out" / "rel"
    proc = cli(*run_args(kit, out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not out.exists()
    assert "rescan.payment-cards" in proc.stdout


def test_spelling_variant_of_a_person_id_is_one_person_via_cli(tmp_path, released):
    """#57: a second spelling (surrounding whitespace) of one person ID is the same person for person-k."""
    _, base_out, base_proc = released
    assert base_proc.returncode == 0

    def plant(folder):
        coarse_qis(folder)
        p = folder / "ed_visits.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        counts = df["patient_hetu"].value_counts()
        dup = sorted(v for v, n in counts.items() if n >= 2 and v)[0]
        i = df.index[df["patient_hetu"] == dup][-1]
        df.loc[i, "patient_hetu"] = f" {dup} "
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    kit = build_kit(tmp_path / "kit", plant)
    out = tmp_path / "out" / "rel"
    proc = cli(*run_args(kit, out))
    assert proc.returncode == 0, proc.stdout + proc.stderr

    def persons(o):
        sup = json.loads((o.parent / "rel.scoring" / "suppression_report.json").read_text(encoding="utf-8"))
        return sup["personKBefore"]["persons"]

    assert persons(out) == persons(base_out)


def test_verify_full_ignores_planted_rowmap(released):
    kit, out, proc = released
    assert proc.returncode == 0
    sc = out.parent / "rel.scoring"
    p = sc / "rowmap_ed_visits.csv"
    orig = p.read_bytes()
    try:
        p.write_text("protected_row,original_record_id\n0,planted\n", encoding="utf-8")
        full = cli("verify", "--full", "--kit", str(kit), str(out))
        assert full.returncode == 0, full.stdout
    finally:
        p.write_bytes(orig)


def test_two_runs_byte_identical(tmp_path, released):
    kit, out, proc = released
    assert proc.returncode == 0
    out2 = tmp_path / "rel2"
    proc2 = cli(*run_args(kit, out2))
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
    assert _digests(out) == _digests(out2)
    m = json.loads((out2 / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert m["release"]["created"] == CREATED
