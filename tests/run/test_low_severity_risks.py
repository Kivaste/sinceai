"""Low-severity gate hits become residual risks with counts (issue #58).

Rule: for every gate check with low-severity hits, the manifest's ``residualRisks`` carries one
``gate_low_severity`` entry per (check, label) with the hit count and the check's denominator (counts only, never
a value); the release is still published. Both verify tiers re-derive those entries from the fresh records and
fail on any difference.

Rows (trigger -> result), real CLI on the synthetic minikit, synthetic rows only:
  health term planted in a released free-text source cell (text.health is low severity for HEALTH-S1)
      -> exit 0, released; residualRisks has gate:text.health:HEALTH with count == gate hits and the gate's
         denominator; the planted term is nowhere in the manifest; limited and full verify exit 0
  that entry's count edited in the signed manifest, re-signed   -> limited verify 1, full verify 1
  clean run (no low hits)                                       -> no gate_low_severity entry
"""
from __future__ import annotations

import json

import pandas as pd
from run_helpers import build_kit, cli, coarse_qis, run_args
from test_verify_assertion_rerun import MANIFEST, resign

PLANTED = "diabetes follow-up panel"  # synthetic; matches the bundled health lexicon (prefix "diabet")
RISK = "gate:text.health:HEALTH"


def _plant(folder):
    coarse_qis(folder)
    p = folder / "lab_results.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    df.loc[0, "test_name"] = PLANTED
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")


def _risks(rel, kind="gate_low_severity"):
    m = json.loads((rel / MANIFEST).read_text(encoding="utf-8"))
    return m, [r for r in m["residualRisks"] if r["kind"] == kind]


def test_low_hit_published_as_counted_residual_risk_and_reverified(tmp_path):
    kit = build_kit(tmp_path / "kit", _plant)
    rel = tmp_path / "out" / "rel"
    proc = cli(*run_args(kit, rel))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    m, low = _risks(rel)
    gate = {g["check"]: g for g in m["gate"]["checks"]}["text.health"]
    assert gate["status"] == "pass" and gate["hits"] >= 1
    by = {r["risk"]: r for r in low}
    assert RISK in by, m["residualRisks"]
    rate = by[RISK]["rate"]
    assert rate["status"] == "counted" and rate["count"] == gate["hits"]
    assert rate["denominator"] == gate["denominator"]
    assert by[RISK]["label"] == "HEALTH"
    assert "diabet" not in (rel / MANIFEST).read_text(encoding="utf-8").lower()

    assert cli("verify", str(rel)).returncode == 0
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 0, full.stdout

    html = tmp_path / "dash" / "dashboard.html"
    dash = cli("dashboard", str(rel), "--out", str(html))
    assert dash.returncode == 0, dash.stdout + dash.stderr
    page = html.read_text(encoding="utf-8")
    assert RISK in page and f"{rate['count']} low-severity hit(s)" in page

    for r in m["residualRisks"]:
        if r["risk"] == RISK:
            r["rate"]["count"] += 1
    (rel / MANIFEST).write_text(json.dumps(m), encoding="utf-8")
    resign(rel)
    lim = cli("verify", str(rel))
    assert lim.returncode == 1 and "residualRisks" in lim.stdout, lim.stdout
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 1 and "residualRisks" in full.stdout, full.stdout


def test_clean_run_has_no_low_severity_entry(released):
    _, out, proc = released
    assert proc.returncode == 0
    _, low = _risks(out)
    assert low == []
