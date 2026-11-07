"""#106 round 2 (the #62 provenance/QI escape) at the CLI seam. Synthetic minikit rows only.

Rule: a released column's declared provenance is never trusted on its own.
  (a) Structure: its source must be a policy column of the same table, its rung must be on that source's ladder at or
      coarser than the policy floor (or exactly the policy's alternative floor), its output name must be the one the
      ladder gives that source (the source name, or the policy's derived name for an age rung), and no source is
      released twice. Otherwise the contract is refused by the writer and by manifest validation (both verify tiers).
  (b) Values: under the gate and ``verify --full`` every released column is reconstructed from the source through its
      declared mapping; a column that does not reproduce has no trusted source and counts as a quasi-identifier, so
      person-k refuses unless k holds over it as released.

Failure rows (trigger -> wrong result before round 2):
  R1 released copy: lab_results gets ``extra_lab`` (another column's values) declaring ``derived_from: ref_range``,
     backed by a field justification, contract digest rebound, re-signed -> both verify tiers exit 0; want exit 1
     naming the unsupported provenance
  R2 released copy: the released ``unit`` values rotated by one row (same name, same rung, values no longer derived
     from the source), re-signed -> verify --full exits 0; want exit 1 naming producer.person-k
  R3 run whose release gains the R1 column before the writer -> released (exit 0); want refused (exit 1), no manifest
"""
from __future__ import annotations

import json

import pandas as pd
from run_helpers import TEST_KEY, build_kit, cli, coarse_qis, run_args
from test_verify_assertion_rerun import MANIFEST, copy_release, resign

from pets_release.manifest import canonical_bytes, canonical_digest

EXTRA = "extra_lab"


def _read(rel, name):
    return pd.read_csv(rel / name, dtype=str, keep_default_na=False, na_filter=False)


def _write(rel, name, df):
    df.to_csv(rel / name, index=False, encoding="utf-8", lineterminator="\n")


def _plant_contract(contract):
    cols = contract["files"]["lab_results.csv"]
    cols["columns"][EXTRA] = {"form": "text", "params": {"derived_from": "ref_range", "nullable": True, "rung": "keep"}}
    cols["required"] = sorted({*cols["required"], EXTRA})


def test_planted_provenance_fails_both_verify_tiers(released, tmp_path):
    kit, rel = copy_release(released, tmp_path)
    df = _read(rel, "lab_results.csv")
    df[EXTRA] = df["test_code"]
    _write(rel, "lab_results.csv", df)
    m = json.loads((rel / MANIFEST).read_text(encoding="utf-8"))
    _plant_contract(m["contract"])
    for f in m["fieldJustifications"]:
        if (f["table"], f["column"]) == ("lab_results", "ref_range"):
            f.update(decision="released", outputColumn=EXTRA, rung="keep")
    m["bindings"]["contractDigest"] = canonical_digest(m["contract"])
    (rel / MANIFEST).write_bytes(canonical_bytes(m))
    resign(rel)
    lim = cli("verify", str(rel))
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    for proc in (lim, full):
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "unsupported-provenance" in proc.stdout, proc.stdout
        assert "VERIFIED" not in proc.stdout.replace("VERIFY FAILED", "")


def test_values_not_derived_from_the_declared_source_fail_full_verify(released, tmp_path):
    kit, rel = copy_release(released, tmp_path)
    df = _read(rel, "lab_results.csv")
    before = df["unit"].tolist()
    df["unit"] = before[1:] + before[:1]
    assert df["unit"].tolist() != before
    _write(rel, "lab_results.csv", df)
    resign(rel)
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 1, full.stdout + full.stderr
    assert "producer.person-k" in full.stdout, full.stdout
    assert "VERIFIED" not in full.stdout.replace("VERIFY FAILED", "")


def test_run_refuses_a_planted_provenance_before_publication(tmp_path, monkeypatch):
    """The production run path; only ``protect``'s output gains the planted column (as a faulty plan step would)."""
    from pets_release.run import cli as run_cli
    from pets_release.run import pipeline

    real = pipeline.protect

    def planted(plan, **kw):
        released, finals, suppressed, sup, contract = real(plan, **kw)
        lab = released["lab_results"].copy()
        lab[EXTRA] = lab["test_code"]
        released = {**released, "lab_results": lab}
        _plant_contract(contract)
        return released, finals, suppressed, sup, contract

    real_narrative = pipeline.build_narrative

    def justified(**kw):  # the planted column is backed by a field justification, as in R1
        n = real_narrative(**kw)
        for f in n["fieldJustifications"]:
            if (f["table"], f["column"]) == ("lab_results", "ref_range"):
                f.update(decision="released", outputColumn=EXTRA, rung="keep")
        return n

    monkeypatch.setattr(pipeline, "protect", planted)
    monkeypatch.setattr(pipeline, "build_narrative", justified)
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", coarse_qis)
    rel = tmp_path / "out" / "rel"
    assert run_cli.main(run_args(kit, rel)[1:]) == 1
    assert not (rel / MANIFEST).exists()
    report = json.loads((rel.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))
    assert any("unsupported-provenance" in r for r in report["reasons"]), report["reasons"]
