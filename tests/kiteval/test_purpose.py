"""Purpose checks from kit utility tasks. Fixtures are tiny hand-made synthetic rows."""

import json

import pandas as pd
import pytest

from pets_release.kiteval.purpose import counts_as_fail, purpose_check, purpose_checks
from pets_release.kiteval.report import ScorecardRejected

ORIG = pd.DataFrame(
    {
        "conversation_id": ["c1", "c2", "c3", "c4"],
        "intent": ["refund", "refund", "billing", "billing"],
        "handle_time_s": ["300", "500", "200", "400"],
    },
    dtype=str,
)


def _tables(df):
    return {"conversations": df}


def test_cs_u4_on_all_string_originals_matches_numerically_typed_originals():
    prot = ORIG.copy()
    typed = ORIG.copy()
    typed["handle_time_s"] = typed["handle_time_s"].astype(int)
    from_strings = purpose_check("CS-U4", _tables(ORIG), _tables(prot))
    from_numbers = purpose_check("CS-U4", _tables(typed), _tables(prot))
    assert from_strings["status"] == "ok"
    assert from_strings["score"] == from_numbers["score"] == 1.0
    assert not pd.api.types.is_numeric_dtype(ORIG["handle_time_s"])  # caller's copy untouched


def test_degraded_protected_values_lower_the_score():
    prot = ORIG.copy()
    prot["handle_time_s"] = ["3000", "5000", "2000", "4000"]
    res = purpose_check("CS-U4", _tables(ORIG), _tables(prot))
    assert res["status"] == "ok" and res["score"] < 1.0


def test_not_answerable_task_is_a_fail():
    prot = ORIG.drop(columns=["handle_time_s"])
    res = purpose_check("CS-U4", _tables(ORIG), _tables(prot))
    assert res["status"] == "not_answerable" and res["score"] is None
    assert counts_as_fail(res)


def test_tables_missing_entirely_is_a_fail():
    assert counts_as_fail(purpose_check("CS-U4", {}, {}))


def test_task_error_is_a_fail_and_carries_no_message(monkeypatch):
    from pets_eval.utility import UtilityTask

    def boom(orig, prot):
        raise ValueError("VALUE_THAT_MUST_NOT_LEAK")

    task = UtilityTask("CS-U4", "customer_service", "conversations", "d", "aggregate", boom)
    monkeypatch.setattr("pets_release.kiteval.purpose.all_tasks", lambda *a, **k: [task])
    res = purpose_check("CS-U4", {}, {})
    assert res == {"id": "CS-U4", "score": None, "status": "error", "required": True}
    assert counts_as_fail(res)
    assert set(res) == {"id", "score", "status", "required"}


def test_unknown_task_is_a_fail():
    res = purpose_check("NO-SUCH-TASK", {}, {})
    assert res["status"] == "missing" and counts_as_fail(res)


def test_ok_result_passes():
    assert not counts_as_fail({"id": "x", "score": 0.0, "status": "ok", "required": True})


@pytest.fixture
def mini_kit(tmp_path):
    (tmp_path / "metadata").mkdir()
    (tmp_path / "metadata" / "scenarios.json").write_text(
        json.dumps([{"id": "TEST-S1", "dataset": "customer_service", "utility_requirements": ["CS-U4", "CS-U99"]}]),
        encoding="utf-8",
    )
    return tmp_path


def test_scenario_tasks_include_missing_required_task_as_failure(mini_kit):
    results = purpose_checks("TEST-S1", _tables(ORIG), _tables(ORIG), root=mini_kit)
    by_id = {r["id"]: r for r in results}
    assert by_id["CS-U4"]["status"] == "ok" and by_id["CS-U4"]["score"] == 1.0
    assert by_id["CS-U99"]["status"] == "missing"
    assert [counts_as_fail(r) for r in results] == [False, True]


def test_unknown_scenario_is_rejected(mini_kit):
    with pytest.raises(ScorecardRejected) as caught:
        purpose_checks("NOPE-S9", {}, {}, root=mini_kit)
    assert caught.value.reason == "scenario"




# ---- review round 2: explicit per-task numeric columns ---------------------


def _spy(monkeypatch, seen, task_id="CS-U4", needs=("intent", "handle_time_s", "agent_note")):
    from pets_eval.utility import UtilityTask

    def fn(orig, prot):
        seen["orig"], seen["prot"] = orig, prot
        return {"score": 1.0, "metric": "m", "detail": {}}

    task = UtilityTask(task_id, "customer_service", "conversations", "d", "aggregate", fn, list(needs))
    monkeypatch.setattr("pets_release.kiteval.purpose.all_tasks", lambda *a, **k: [task])


def test_only_the_tasks_numeric_measures_become_numbers(monkeypatch):
    seen = {}
    _spy(monkeypatch, seen)
    df = pd.DataFrame({"intent": ["001", "002", "003"], "handle_time_s": ["10", "20", ""],
                       "agent_note": ["007", "0123", "42"]}, dtype=str)
    res = purpose_check("CS-U4", {"conversations": df}, {"conversations": df})
    assert res["status"] == "ok"
    for side in ("orig", "prot"):
        t = seen[side]["conversations"]
        assert list(t["intent"]) == ["001", "002", "003"]  # numeric-looking category stays a string
        assert list(t["agent_note"]) == ["007", "0123", "42"]  # so does text, though the task lists it
        assert pd.api.types.is_numeric_dtype(t["handle_time_s"]) and t["handle_time_s"].isna().sum() == 1
    assert list(df["intent"]) == ["001", "002", "003"]


def test_numeric_looking_categories_are_not_collapsed_for_the_mix_task(monkeypatch):
    seen = {}
    _spy(monkeypatch, seen, task_id="CS-U3", needs=("intent",))
    orig = pd.DataFrame({"intent": ["01", "1", "1"]}, dtype=str)
    prot = pd.DataFrame({"intent": ["1", "1", "1"]}, dtype=str)
    purpose_check("CS-U3", {"conversations": orig}, {"conversations": prot})
    assert list(seen["orig"]["conversations"]["intent"]) == ["01", "1", "1"]
    assert list(seen["prot"]["conversations"]["intent"]) == ["1", "1", "1"]


def test_task_without_a_numeric_column_entry_is_an_error_not_a_guess(monkeypatch):
    seen = {}
    _spy(monkeypatch, seen, task_id="NEW-U1")
    res = purpose_check("NEW-U1", {"conversations": ORIG}, {"conversations": ORIG})
    assert res["status"] == "error" and counts_as_fail(res)
    assert not seen  # never ran on guessed types
