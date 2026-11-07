"""Measurer against the real kit. Skipped when the kit is absent (PETS_KIT, else the conventions path).

The baseline literals are the 2-decimal HEALTH-S1 / CS-S1 rows of docs/BENCHMARK.md (utility per sharing
scenario: B0, B2, B2-k). The measure() test runs the kit's own B2 protector (baselines/protect.py) and
measures its outputs; nothing here prints or stores a kit value."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from pets_release.kiteval import Lineage
from pets_release.measure import baseline_rows, measure, measured_errors
from pets_release.measure.baselines import composite
from pets_release.measure.ids import PRIVACY_IDS

_DEFAULT_KIT = Path(r"C:\Users\kivas\AI\sinceai-hackaton\Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)"
                    r"\TRUSTED_PETS_PROVING_GROUND_2026")
KIT = Path(os.environ.get("PETS_KIT") or _DEFAULT_KIT)

PUBLISHED = {  # scenario -> dataset, (B0, B2, B2-k) utility
    "HEALTH-S1": ("health", (1.00, 0.79, 0.40)),
    "CS-S1": ("customer_service", (1.00, 0.75, 0.75)),
}

# Scenarios whose required tasks the kit's own B2 protector can answer (B2 on HEALTH-S1 / CS-S1 cannot answer
# a required task, and the adapter rightly refuses to score such a release).
MEASURE_CASES = {"HEALTH-S3": "health", "CS-S3": "customer_service"}


def _need_kit():
    """Kept for the call sites; the autouse ``kit`` fixture in tests/conftest.py already fails when the kit is absent."""
    assert (KIT / "results" / "benchmark.json").is_file(), "kit required but not found"


@pytest.mark.kit
@pytest.mark.parametrize("scenario", sorted(PUBLISHED))
def test_baseline_utility_matches_published_table(scenario):
    _need_kit()
    dataset, expected = PUBLISHED[scenario]
    rows = {(r["baseline"], r["metric"]): r["value"] for r in baseline_rows(KIT, scenario, dataset)}
    got = tuple(round(rows[(b, "utility_mean")], 2) for b in ("B0", "B2", "B2-k"))
    assert got == expected  # docs/BENCHMARK.md cross-check only; the exact check is below
    # Authoritative values: the kit's own published results/benchmark.json, read independently of baseline_rows.
    # baseline_rows only copies these floats (float(v), no arithmetic), so equality must be EXACT (==, no
    # tolerance): any rounding, scaling or wrong-scenario pick in the production code changes the value.
    pub = json.loads((KIT / "results" / "benchmark.json").read_text(encoding="utf-8"))["baselines"]
    for baseline, prefix in (("B0", "B0"), ("B2", "B2"), ("B2-k", "B2K")):
        rec = pub[f"{prefix}_{dataset}"]
        assert rows[(baseline, "utility_mean")] == rec["utility_by_scenario"][scenario]
        assert rows[(baseline, "privacy")] == rec["privacy"]
        assert rows[(baseline, "worst_reid")] == rec["worst_reid"]
        assert rows[(baseline, "composite")] == pytest.approx(
            composite(rec["privacy"], rec["utility_by_scenario"][scenario]), abs=1e-12)  # same formula, same floats


@pytest.mark.kit
@pytest.mark.parametrize("scenario", sorted(MEASURE_CASES))
def test_measure_on_the_kits_b2_outputs_validates(scenario, tmp_path):
    _need_kit()
    dataset = MEASURE_CASES[scenario]
    raw = tmp_path / "b2"
    proc = subprocess.run([sys.executable, str(KIT / "baselines" / "protect.py"), "--level", "b2", "--dataset",
                           dataset, "--scenario", scenario, "--out", str(raw)], cwd=KIT, capture_output=True,
                          env={**os.environ, "PYTHONUTF8": "1"}, check=False)
    assert proc.returncode == 0
    release, maps = tmp_path / "release" / dataset, tmp_path / "scoring"
    release.mkdir(parents=True)
    maps.mkdir()
    rowmaps, lineage = {}, {}
    for f in sorted(raw.glob("*.csv")):
        if f.name.startswith("rowmap_"):
            table = f.stem[len("rowmap_"):]
            f.replace(maps / f.name)
            rowmaps[table] = maps / f.name
            ids = pd.read_csv(maps / f.name, dtype=str, keep_default_na=False)["original_record_id"]
            lineage[table] = Lineage(tuple(ids), frozenset())
        else:
            f.replace(release / f.name)
    with (KIT / "metadata" / "field_catalog.csv").open(encoding="utf-8", newline="") as fh:
        keys = {r["table"]: r["column"] for r in csv.DictReader(fh)
                if r["dataset"] == dataset and r["privacy_role"] == "record_key"}
    out = (Path(os.environ["PETS_MEASURE_OUT"]) / scenario) if os.environ.get("PETS_MEASURE_OUT") else tmp_path / "out"
    block = measure(scenario, root=KIT, original_dir=KIT / "data" / dataset, protected_dir=release,
                    rowmaps=rowmaps, lineage=lineage, record_keys=keys, out_dir=out)
    assert measured_errors(block) == []
    assert block["utility"]["status"] == block["privacy"]["status"] == block["baselines"]["status"] == "measured"
    comps = {c["component"]: c for c in block["privacy"]["components"]}
    assert set(PRIVACY_IDS) <= set(comps)  # the ids the story kit template reads
    assert all(comps[i]["before"] is not None and comps[i]["after"] is not None for i in PRIVACY_IDS)
    assert not any(c.startswith("summary.") for c in comps)
    assert all(t["before"] is not None for t in block["utility"]["tasks"])
    # (1) Measured "after" must equal the kit's own pets-eval scorecard summary for the same files. measure()
    # copies these floats from the scorecard it just wrote (no arithmetic), so the tolerance is exact equality.
    for side, path in (("after", out / "after" / "scorecard.json"),
                       ("before", out / "before" / "kit-out" / "scorecard.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))["summary"]
        assert comps["privacy"][side] == summary["privacy"]
    kit_tasks = {t["id"]: t["score"] for t in json.loads(
        (out / "after" / "scorecard.json").read_text(encoding="utf-8"))["utility"]}
    assert {t["task"]: t["after"] for t in block["utility"]["tasks"]} == kit_tasks
    mean_after = sum(t["after"] for t in block["utility"]["tasks"]) / len(block["utility"]["tasks"])
    assert mean_after == pytest.approx(json.loads((out / "after" / "scorecard.json").read_text(
        encoding="utf-8"))["summary"]["utility"], abs=1e-9)  # mean of identical floats, summation order only
    # (2) Our rerun of the kit's B2 protector vs the kit's PUBLISHED B2 row. The published file stores 4
    # decimals, so the tightest meaningful tolerance is half a unit of the last place (5e-5), not 0.02.
    published = {(r["baseline"], r["metric"]): r["value"] for r in block["baselines"]["rows"]}
    assert abs(mean_after - published[("B2", "utility_mean")]) <= 5e-5
    assert abs(comps["privacy"]["after"] - published[("B2", "privacy")]) <= 5e-5


@pytest.mark.kit
@pytest.mark.parametrize("dataset", sorted({d for d, _ in PUBLISHED.values()}))
def test_composite_formula_reproduces_the_published_dataset_wide_composite(dataset):
    import json
    _need_kit()
    from pets_release.measure.baselines import composite
    published = json.loads((KIT / "results" / "benchmark.json").read_text(encoding="utf-8"))["baselines"]
    for prefix in ("B0", "B2", "B2K"):
        rec = published[f"{prefix}_{dataset}"]
        assert composite(rec["privacy"], rec["utility"]) == pytest.approx(rec["composite"], abs=0.005)
