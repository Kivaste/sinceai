"""Must-fix follow-up 52: full-table "before", consistent person-k, scenario baselines, [0,1] scores."""

from __future__ import annotations

import json
import shutil

import pandas as pd
import pytest

from pets_release.checks.producer.kanon import PersonK
from pets_release.measure import MeasureRejected, baseline_rows, measure, person_k_components
from pets_release.measure.baselines import composite

SCENARIO = "TEST-S1"  # defined by tests/measure/conftest.py's kit
ROWS = [("c1", "refund", "300"), ("c2", "refund", "500"), ("c3", "billing", "200"), ("c4", "billing", "400")]


def write_table(path, rows):
    pd.DataFrame(rows, columns=["conversation_id", "intent", "handle_time_s"], dtype=str).to_csv(path, index=False)


def _pk(values, unidentified=0):
    return PersonK({f"p{i}": v for i, v in enumerate(values)}, [], unidentified, [])


# 1. "before" keeps tables the release withholds --------------------------------------------------------
def test_before_is_built_from_every_original_table_even_if_one_is_withheld(args, kit):
    with (kit / "metadata" / "field_catalog.csv").open("a", encoding="utf-8") as f:
        f.write("customer_service,customers,conversation_id,record_key,identifier,id\n")
    write_table(kit / "data" / "customer_service" / "customers.csv", ROWS)
    rk = {**args["record_keys"], "customers": "conversation_id"}
    block = measure(SCENARIO, **{**args, "record_keys": rk})  # release holds conversations only
    inputs = args["out_dir"] / "before" / "inputs"
    assert sorted(p.name for p in (inputs / "release").iterdir()) == ["conversations.csv", "customers.csv"]
    assert sorted(p.name for p in (inputs / "rowmaps").iterdir()) == [
        "rowmap_conversations.csv", "rowmap_customers.csv"]
    before = json.loads((args["out_dir"] / "before" / "kit-out" / "scorecard.json").read_text(encoding="utf-8"))
    after = json.loads((args["out_dir"] / "after" / "scorecard.json").read_text(encoding="utf-8"))
    assert {"conversations", "customers"} <= set(before["tables"])
    assert after["tables"]["customers"]["status"] == "withheld" and before["tables"]["customers"]["status"] != "withheld"
    ids = {c["component"] for c in block["privacy"]["components"]}
    assert any(i.startswith("risk.customers") for i in ids)  # the withheld table's risk is in "before"
    withheld = [c for c in block["privacy"]["components"] if c["component"].startswith("risk.customers")]
    assert withheld and all(c["before"] is not None for c in withheld)


def test_original_table_without_a_record_key_fails(args, kit):
    write_table(kit / "data" / "customer_service" / "customers.csv", ROWS)
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)  # record_keys has no entry for the extra original table
    assert caught.value.reason == "record_key"


# 2. person-k min / below-k are consistent --------------------------------------------------------------
def test_min_is_not_measured_when_units_are_unidentified():
    by = {c["component"]: c for c in person_k_components(_pk([5, 6, 7], unidentified=1), k=5)}
    assert by["person_k.below_k_share"]["after"] == 0.25
    assert by["person_k.min"]["after"] is None  # no fabricated value
    assert by["person_k.persons"]["after"] == 4.0


def test_min_is_the_smallest_k_when_everyone_is_identified():
    by = {c["component"]: c for c in person_k_components(_pk([3, 6]), k=5)}
    assert by["person_k.min"]["after"] == 3.0 and by["person_k.below_k_share"]["after"] == 0.5


def test_only_unidentified_units_gives_share_one_and_no_min():
    by = {c["component"]: c for c in person_k_components(_pk([], unidentified=2), k=5)}
    assert by["person_k.below_k_share"]["after"] == 1.0 and by["person_k.min"]["after"] is None


@pytest.mark.parametrize("bad", [0, -1, 2.5, True, None, "3"])
def test_per_person_values_must_be_ints_at_least_one(bad):
    with pytest.raises(MeasureRejected) as caught:
        person_k_components(_pk([5, bad]), k=5)
    assert caught.value.reason == "person_k"


def test_person_k_block_with_null_min_still_validates(args):
    from pets_release.measure import measured_errors
    block = measure(SCENARIO, person_k=person_k_components(_pk([5], unidentified=1), k=5), **args)
    assert measured_errors(block) == []


# 3. baselines use the scenario's published utility -----------------------------------------------------
def _set_bench(kit, mutate):
    p = kit / "results" / "benchmark.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    mutate(d["baselines"])
    p.write_text(json.dumps(d), encoding="utf-8")


def test_baseline_utility_is_the_scenario_value_not_the_dataset_wide_one(kit):
    def mutate(b):
        b["B2_customer_service"]["utility"] = 0.9  # dataset-wide, all tasks
        b["B2_customer_service"]["utility_by_scenario"][SCENARIO] = 0.6
    _set_bench(kit, mutate)
    rows = {(r["baseline"], r["metric"]): r["value"] for r in baseline_rows(kit, SCENARIO, "customer_service")}
    assert rows[("B2", "utility_mean")] == 0.6
    assert rows[("B2", "composite")] == pytest.approx(55 / (30 / 0.5 + 25 / 0.6))
    assert ("B2", "utility") not in rows


def test_composite_is_the_kit_weighted_harmonic_mean():
    assert composite(1.0, 1.0) == pytest.approx(1.0)
    assert composite(0.0, 1.0) == 0.0
    assert composite(0.5, 0.5) == pytest.approx(0.5)


@pytest.mark.parametrize("field,value", [("privacy", 1.5), ("worst_reid", -0.1), ("utility_by_scenario", 2.0)])
def test_out_of_range_published_baseline_fails(kit, field, value):
    def mutate(b):
        rec = b["B2_customer_service"]
        if field == "utility_by_scenario":
            rec[field][SCENARIO] = value
        else:
            rec[field] = value
    _set_bench(kit, mutate)
    with pytest.raises(MeasureRejected) as caught:
        baseline_rows(kit, SCENARIO, "customer_service")
    assert caught.value.reason == "baseline_range"


def test_published_null_scenario_utility_fails(kit):
    _set_bench(kit, lambda b: b["B2_customer_service"]["utility_by_scenario"].__setitem__(SCENARIO, None))
    with pytest.raises(MeasureRejected):
        baseline_rows(kit, SCENARIO, "customer_service")


# 5. score range, task ids, not_answerable before ---------------------------------------------------------
def _patched(monkeypatch, edit, *, only_call=None):
    from pets_release.measure import core
    real, calls = core.run_scorecard, []

    def run(*a, **k):
        s = real(*a, **k)
        calls.append(1)
        if only_call is None or len(calls) == only_call:
            edit(s)
        return s
    monkeypatch.setattr(core, "run_scorecard", run)


@pytest.mark.parametrize("value", [1.5, -0.2, 2])
@pytest.mark.parametrize("where", ["privacy", "utility", "composite"])
def test_out_of_range_summary_score_fails(args, monkeypatch, where, value):
    _patched(monkeypatch, lambda s: s.__setitem__(where, value))
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "score"


def test_out_of_range_task_score_fails(args, monkeypatch):
    _patched(monkeypatch, lambda s: s["tasks"][0].__setitem__("score", 1.2))
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "score"


def test_out_of_range_risk_fails(args, monkeypatch):
    _patched(monkeypatch, lambda s: s["risks"].__setitem__("t: records with k<5", 3.0))
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "score"


# 6. k<5 aggregate: row-weighted share and worst table, both pinned ---------------------------------------
def _two_tables(rates, rows, *, status="released"):
    """Hand-made summary edit: tables a and b with k<5 rates and row counts, nothing else k-related."""
    def edit(s):
        for key in [k for k in s["risks"] if k.endswith(": records with k<5")]:
            del s["risks"][key]
        s["tables"] = [{"table": t, "status": status, "rows_original": n, "rows_protected": n}
                       for t, n in rows.items()]
        for t, r in rates.items():
            s["risks"][f"{t}: records with k<5"] = r
    return edit


def _component(block, cid):
    return next(c for c in block["privacy"]["components"] if c["component"] == cid)


def test_k_below_5_share_is_row_weighted_and_the_worst_table_is_kept_apart(args, monkeypatch):
    # a: 10 rows at 0.5 -> 5 rows below 5; b: 90 rows at 0.0. max = 0.5, row-weighted = 5/100
    _patched(monkeypatch, _two_tables({"a": 0.5, "b": 0.0}, {"a": 10, "b": 90}))
    block = measure(SCENARIO, **args)
    assert _component(block, "k_below_5_share")["after"] == pytest.approx(0.05)
    assert _component(block, "k_below_5_share")["before"] == pytest.approx(0.05)
    assert _component(block, "k_below_5_worst_table")["after"] == 0.5
    assert _component(block, "k_below_5_worst_table")["before"] == 0.5


def test_k_below_5_weighted_share_uses_each_tables_row_count(args, monkeypatch):
    _patched(monkeypatch, _two_tables({"a": 0.2, "b": 1.0}, {"a": 80, "b": 20}))  # (16 + 20) / 100
    assert _component(measure(SCENARIO, **args), "k_below_5_share")["after"] == pytest.approx(0.36)


@pytest.mark.parametrize("rows_protected", [None, 0, -3, 2.5, True, "10"])
def test_k_below_5_share_fails_closed_on_a_bad_row_count(args, monkeypatch, rows_protected):
    edit = _two_tables({"a": 0.5, "b": 0.0}, {"a": 10, "b": 90})

    def bad(s):
        edit(s)
        s["tables"][0]["rows_protected"] = rows_protected
    _patched(monkeypatch, bad)
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "risk_rows"


def test_k_below_5_share_fails_closed_when_a_rate_has_no_table_row_count(args, monkeypatch):
    def bad(s):
        _two_tables({"a": 0.5}, {"a": 10})(s)
        s["risks"]["ghost: records with k<5"] = 0.1  # no such table in the summary
    _patched(monkeypatch, bad)
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "risk_rows"


def test_a_released_table_with_no_k_rate_is_excluded_and_the_weighted_tables_are_listed(args, monkeypatch):
    # b is released but not scored for k (no rate): excluded from the weighting, not an error
    _patched(monkeypatch, _two_tables({"a": 0.5, "c": 0.1}, {"a": 10, "b": 500, "c": 30}))
    block = measure(SCENARIO, **args)
    share = _component(block, "k_below_5_share")
    assert share["after"] == pytest.approx((5 + 3) / 40) and share["before"] == pytest.approx((5 + 3) / 40)
    assert _component(block, "k_below_5_worst_table")["after"] == 0.5
    assert "row-weighted over the tables scored for k: before=a,c after=a,c" in block["privacy"]["source"]


def test_a_rate_for_a_withheld_table_fails_closed(args, monkeypatch):
    def bad(s):
        _two_tables({"a": 0.5, "b": 0.2}, {"a": 10, "b": 90})(s)
        s["tables"][1]["status"] = "withheld"
        s["tables"][1]["rows_protected"] = None
    _patched(monkeypatch, bad)
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "risk_rows"


def test_no_k_rate_anywhere_means_not_measured_and_no_table_note(args):
    block = measure(SCENARIO, **args)  # the synthetic kit reports no k<5 rate
    ids = {c["component"] for c in block["privacy"]["components"]}
    assert "k_below_5_share" not in ids and "row-weighted" not in block["privacy"]["source"]


def test_task_without_an_id_is_a_measure_rejection_not_a_keyerror(args, monkeypatch):
    _patched(monkeypatch, lambda s: s["tasks"][0].pop("id"))
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "task_status"


def test_not_answerable_before_is_rejected(args, monkeypatch):
    def edit(s):
        s["tasks"][0]["status"] = "not_answerable"
        s["tasks"][0]["score"] = None
    _patched(monkeypatch, edit, only_call=2)  # the second run is "before"
    with pytest.raises(MeasureRejected) as caught:
        measure(SCENARIO, **args)
    assert caught.value.reason == "before_not_answerable"


def test_not_answerable_after_with_an_answerable_before_is_kept(args, monkeypatch):
    def edit(s):
        s["tasks"][0]["status"] = "not_answerable"
        s["tasks"][0]["score"] = None
    _patched(monkeypatch, edit, only_call=1)  # the first run is "after"
    block = measure(SCENARIO, **args)
    assert block["utility"]["tasks"] == [{"task": "CS-U4", "status": "not_answerable", "before": 1.0, "after": None}]


def test_release_dir_untouched_by_before_stand_in(args):
    measure(SCENARIO, **args)
    assert not any(p.name.startswith("rowmap_") for p in args["protected_dir"].iterdir())
    shutil.rmtree(args["out_dir"])


@pytest.mark.parametrize("value", ["absent", None, "x", {}, [], [""], [1]])
def test_missing_or_malformed_utility_requirements_is_rejected(kit, value):
    p = kit / "metadata" / "scenarios.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    if value == "absent":
        del s[0]["utility_requirements"]
    else:
        s[0]["utility_requirements"] = value
    p.write_text(json.dumps(s), encoding="utf-8")
    with pytest.raises(MeasureRejected) as caught:
        baseline_rows(kit, SCENARIO, "customer_service")
    assert caught.value.reason == "baseline_structure"