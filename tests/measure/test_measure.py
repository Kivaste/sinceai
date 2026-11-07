"""The measurer fills `measured.*` through the real kit-eval adapter on the synthetic kit."""

from __future__ import annotations

import copy

import pytest
from jsonschema import Draft202012Validator

from pets_release.kiteval import ScorecardRejected
from pets_release.manifest import MANIFEST_SCHEMA
from pets_release.measure import MeasureRejected, measure, measured_errors

SCENARIO = "TEST-S1"  # defined by tests/measure/conftest.py's kit


def test_block_validates_against_the_manifest_measured_schema(args):
    block = measure(SCENARIO, **args)
    assert measured_errors(block) == []
    Draft202012Validator({"$defs": MANIFEST_SCHEMA["$defs"], **MANIFEST_SCHEMA["properties"]["measured"]}
                         ).validate(block)
    assert set(block) == {"utility", "privacy", "search", "baselines", "redaction"}
    assert block["search"]["status"] == "not_measured" and block["redaction"]["status"] == "not_measured"


def test_validator_is_real_not_vacuous(args):
    block = measure(SCENARIO, **args)
    bad = copy.deepcopy(block)
    bad["utility"]["tasks"][0]["status"] = "bogus"
    assert measured_errors(bad)
    bad = copy.deepcopy(block)
    bad["extra"] = 1
    assert measured_errors(bad)


def test_before_and_after_scores_come_from_two_scorecard_runs(args):
    block = measure(SCENARIO, **args)
    assert block["utility"]["status"] == "measured"
    assert block["utility"]["tasks"] == [{"task": "CS-U4", "status": "ok", "before": 1.0, "after": 1.0}]
    comps = {c["component"]: c for c in block["privacy"]["components"]}
    assert {"summary.privacy", "summary.composite", "summary.utility"} <= set(comps)
    assert comps["summary.utility"]["before"] == 1.0 and comps["summary.utility"]["after"] == 1.0
    # identical release: the privacy score cannot differ between the two runs
    assert comps["summary.privacy"]["before"] == comps["summary.privacy"]["after"]
    out = args["out_dir"]
    assert (out / "after" / "scorecard.json").is_file() and (out / "before" / "kit-out" / "scorecard.json").is_file()


def test_components_are_sorted_with_valid_unique_ids(args):
    block = measure(SCENARIO, **args)
    ids = [c["component"] for c in block["privacy"]["components"]]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    rows = [(r["baseline"], r["metric"]) for r in block["baselines"]["rows"]]
    assert rows == sorted(rows)


def test_wrong_scenario_id_fails(args):
    with pytest.raises(ScorecardRejected) as caught:
        measure("CS-S1", **args)
    assert caught.value.reason == "scenario"


@pytest.mark.parametrize("bad", [None, "", "  ", 7])
def test_missing_scenario_id_fails(args, bad):
    with pytest.raises(MeasureRejected) as caught:
        measure(bad, **args)
    assert caught.value.reason == "scenario"


def test_scenario_missing_from_published_baselines_fails(args, kit):
    import json
    p = kit / "results" / "benchmark.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    del d["baselines"]["B2_customer_service"]["utility_by_scenario"][SCENARIO]
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "baseline_scenario"


def test_missing_baseline_file_fails(args, kit):
    (kit / "results" / "benchmark.json").unlink()
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "baseline_missing"


def test_baseline_rows_hold_the_published_numbers(args):
    block = measure(SCENARIO, **args)
    rows = {(r["baseline"], r["metric"]): r["value"] for r in block["baselines"]["rows"]}
    assert rows[("B0", "privacy")] == 0.25 and rows[("B2", "privacy")] == 0.5 and rows[("B2-k", "privacy")] == 0.75
    assert rows[("B0", f"utility.{SCENARIO}")] == 1.0
    assert rows[("B2", f"utility.{SCENARIO}")] == 0.75
    assert rows[("B2-k", f"utility.{SCENARIO}")] == 0.5
    assert rows[("B2", "task.CS-U4")] is None  # published as not answerable: stays null, never 0
    assert rows[("B2-k", "worst_reid")] == 0.0


def test_errored_scorecard_fails_instead_of_writing_zeros(args, monkeypatch):
    def boom(*a, **k):
        raise ScorecardRejected("error_status")
    monkeypatch.setattr("pets_release.measure.core.run_scorecard", boom)
    with pytest.raises(ScorecardRejected):
        measure(SCENARIO, **args)


def test_error_task_in_a_summary_fails(args, monkeypatch):
    from pets_release.measure import core
    real = core.run_scorecard

    def errored(*a, **k):
        s = real(*a, **k)
        s["tasks"][0]["status"] = "error"
        s["tasks"][0]["score"] = None
        return s
    monkeypatch.setattr(core, "run_scorecard", errored)
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "task_status"


def test_summary_for_another_scenario_fails(args, monkeypatch):
    from pets_release.measure import core
    real = core.run_scorecard

    def other(*a, **k):
        s = real(*a, **k)
        s["scenario"] = "HEALTH-S1"
        return s
    monkeypatch.setattr(core, "run_scorecard", other)
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "scenario"


def test_before_after_task_sets_must_match(args, monkeypatch):
    from pets_release.measure import core
    real = core.run_scorecard
    calls = []

    def uneven(*a, **k):
        s = real(*a, **k)
        calls.append(1)
        if len(calls) == 2:
            s["tasks"] = s["tasks"] + [{"id": "CS-X", "score": 0.5, "required": False, "status": "ok"}]
        return s
    monkeypatch.setattr(core, "run_scorecard", uneven)
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "task_mismatch"


def test_nan_or_out_of_range_score_fails(args, monkeypatch):
    from pets_release.measure import core
    real = core.run_scorecard

    def nan(*a, **k):
        s = real(*a, **k)
        s["utility"] = float("nan")
        return s
    monkeypatch.setattr(core, "run_scorecard", nan)
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "score"


def test_original_dir_not_named_like_the_scenario_dataset_fails(args, tmp_path):
    import shutil
    other = tmp_path / "elsewhere"
    shutil.copytree(args["original_dir"], other)
    with pytest.raises(ScorecardRejected) as caught:
        measure(SCENARIO, **{**args, "original_dir": other})
    assert caught.value.reason == "scenario"


def test_release_dir_is_never_written_into(args):
    measure(SCENARIO, **args)
    assert sorted(p.name for p in args["protected_dir"].iterdir()) == ["conversations.csv"]
