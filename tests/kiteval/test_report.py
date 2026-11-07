"""Scorecard report gate: a missing task, an error status, or a zero denominator is a fail."""

import json

import pytest

from pets_release.kiteval.report import ScorecardRejected, validate_report

REQUIRED = ("H-U2", "H-U4")
TABLES = ("ed_visits", "lab_results")


def _passing_report() -> dict:
    return {
        "tool": "pets-eval 1.0.0",
        "dataset": "health",
        "scenario": {"id": "HEALTH-S1", "title": "fixture"},
        "original": "data/health",
        "protected": "out/health",
        "tables": {
            "ed_visits": {
                "table": "ed_visits",
                "status": "released",
                "rows_original": 4,
                "rows_protected": 4,
                "k_anonymity": {"n": 4, "min_k": 2, "share_below": {"k<5": 0.5}},
                "free_text": {
                    "chief_complaint": {
                        "evaluated": True,
                        "n_values": 3,
                        "identifying_leakage_rate": 0.0,
                        "per_label": {"PERSON": {"n": 3, "leaked": 0, "rate": 0.0}},
                    }
                },
                "linkage": {
                    "news_clips_health": {
                        "evaluated": True,
                        "n_targets_in_data": 2,
                        "reidentification_rate": 0.0,
                    }
                },
                "regex_residuals": {"note_text": {"EMAIL": 1}},
                "direct_identifiers_retained": {},
                "risks": {"records with k<5": 0.5},
            },
            "lab_results": {
                "table": "lab_results",
                "status": "withheld",
                "rows_original": 3,
            },
        },
        "utility": [
            {
                "id": "H-U2",
                "score": 1.0,
                "metric": "mean relative error of median LOS by triage",
                "required": True,
                "detail": {"rel_error": 0.0, "orig": {"red": "MARKER_SHOULD_NOT_EXPORT"}},
                "description": "Median length of stay by triage level",
            },
            {
                "id": "H-U4",
                "score": 0.9,
                "metric": "diagnosis-group mix",
                "required": True,
                "detail": {},
                "description": "Diagnosis-group mix",
            },
        ],
        "summary": {
            "privacy": 0.5,
            "utility": 0.95,
            "composite": 0.7,
            "label": "self-assessment, not the official judging score",
            "method": "fixture",
        },
        "risk_components": {"ed_visits: records with k<5": 0.5},
        "examples": [{"value": "MARKER_SHOULD_NOT_EXPORT"}],
        "extra_protected_files": [],
    }


def _validate(report: dict) -> dict:
    return validate_report(
        report,
        scenario="HEALTH-S1",
        required_tasks=REQUIRED,
        tables=TABLES,
    )


def test_missing_task_is_a_fail_not_a_pass():
    report = _passing_report()
    report["utility"] = [u for u in report["utility"] if u["id"] != "H-U4"]
    # The kit still writes a summary and exits 0. That must not become a pass.
    assert report["summary"]["utility"] == 0.95
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "missing_task"


def test_error_status_is_a_fail_not_a_pass():
    report = _passing_report()
    report["utility"][0] = {
        "id": "H-U2",
        "score": None,
        "metric": "error",
        "required": True,
        "detail": {"error": "MARKER_SHOULD_NOT_EXPORT", "trace": "MARKER_SHOULD_NOT_EXPORT"},
    }
    assert report["summary"]["composite"] == 0.7
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "error_status"


def test_table_error_status_is_a_fail_not_a_pass():
    report = _passing_report()
    report["tables"]["ed_visits"] = {
        "table": "ed_visits",
        "status": "error",
        "error": "MARKER_SHOULD_NOT_EXPORT",
        "trace": "MARKER_SHOULD_NOT_EXPORT",
    }
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "error_status"


def test_zero_denominator_leakage_is_a_fail_not_a_pass():
    report = _passing_report()
    report["tables"]["ed_visits"]["free_text"]["chief_complaint"] = {
        "evaluated": True,
        "n_values": 0,
        "identifying_leakage_rate": 0.0,
        "leakage_rate": 0.0,
    }
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "zero_denominator"


def test_zero_denominator_k_anonymity_is_a_fail():
    report = _passing_report()
    report["tables"]["ed_visits"]["k_anonymity"] = {"n": 0, "share_below": {"k<5": 0.0}}
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "zero_denominator"


def test_zero_denominator_linkage_is_a_fail():
    report = _passing_report()
    report["tables"]["ed_visits"]["linkage"] = {
        "news_clips_health": {
            "evaluated": True,
            "n_targets_in_data": 0,
            "reidentification_rate": 0.0,
        }
    }
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "zero_denominator"


def test_exported_summary_is_allowlisted_and_drops_raw_fields():
    summary = _validate(_passing_report())
    assert set(summary) == {
        "scenario",
        "dataset",
        "privacy",
        "utility",
        "composite",
        "tasks",
        "risks",
        "tables",
        "not_applicable",
    }
    assert summary["scenario"] == "HEALTH-S1"
    assert summary["privacy"] == 0.5
    assert summary["utility"] == 0.95
    assert summary["composite"] == 0.7
    assert summary["tasks"] == [
        {"id": "H-U2", "score": 1.0, "required": True, "status": "ok"},
        {"id": "H-U4", "score": 0.9, "required": True, "status": "ok"},
    ]
    assert summary["risks"] == {"ed_visits: records with k<5": 0.5}
    assert summary["tables"] == [
        {"table": "ed_visits", "status": "released", "rows_original": 4, "rows_protected": 4},
        {"table": "lab_results", "status": "withheld", "rows_original": 3, "rows_protected": None},
    ]
    blob = json.dumps(summary, sort_keys=True)
    assert "MARKER_SHOULD_NOT_EXPORT" not in blob
    assert "trace" not in blob
    assert "examples" not in blob
    assert "regex_residuals" not in blob
    assert "detail" not in blob


def test_missing_summary_is_a_fail_not_zeros():
    report = _passing_report()
    del report["summary"]
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "structure"


def test_wrong_scenario_id_is_a_fail():
    report = _passing_report()
    report["scenario"] = {"id": "HEALTH-S2"}
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "scenario"


def test_unscored_required_task_is_a_fail():
    report = _passing_report()
    report["utility"][1]["score"] = None
    report["utility"][1]["metric"] = "not answerable"
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == "not_scored"


def test_withheld_text_without_denominator_is_not_a_zero_denominator_fail():
    report = _passing_report()
    report["tables"]["ed_visits"]["free_text"]["chief_complaint"] = {
        "evaluated": True,
        "status": "withheld",
        "identifying_leakage_rate": 0.0,
    }
    summary = _validate(report)
    assert summary["scenario"] == "HEALTH-S1"


# ---- review round 1 -------------------------------------------------------


def _reject(mutate, reason):
    report = _passing_report()
    mutate(report)
    with pytest.raises(ScorecardRejected) as caught:
        _validate(report)
    assert caught.value.reason == reason


def _ed(report):
    return report["tables"]["ed_visits"]


def test_caught_attack_failure_in_linkage_is_a_fail():
    def m(r):
        _ed(r)["linkage"]["news_clips_health"] = {"evaluated": False, "reason": "error: MARKER_SHOULD_NOT_EXPORT"}

    _reject(m, "error_status")


def test_text_not_evaluated_for_lack_of_row_map_is_a_fail():
    def m(r):
        _ed(r)["free_text"]["chief_complaint"] = {"evaluated": False, "reason": "needs a row map to align texts"}

    _reject(m, "not_evaluated")


def test_nested_trace_anywhere_is_a_fail():
    def m(r):
        _ed(r)["hash_attack"] = {"col": {"trace": "MARKER_SHOULD_NOT_EXPORT"}}

    _reject(m, "error_status")


def test_missing_k_anonymity_record_is_a_fail():
    _reject(lambda r: _ed(r).pop("k_anonymity"), "missing_section")


def test_k_anonymity_without_denominator_or_note_is_a_fail():
    _reject(lambda r: _ed(r).update(k_anonymity={"min_k": 2}), "structure")


def test_released_table_without_scored_risks_is_a_fail():
    _reject(lambda r: _ed(r).pop("risks"), "missing_section")


def test_zero_protected_rows_is_a_fail():
    _reject(lambda r: _ed(r).update(rows_protected=0), "zero_denominator")


def test_missing_protected_rows_is_a_fail():
    _reject(lambda r: _ed(r).pop("rows_protected"), "structure")


def test_linkage_without_target_count_is_a_fail():
    def m(r):
        _ed(r)["linkage"]["news_clips_health"] = {"evaluated": True, "reidentification_rate": 0.0}

    _reject(m, "structure")


def test_free_text_record_without_evaluated_flag_is_a_fail():
    _reject(lambda r: _ed(r)["free_text"].update(chief_complaint={"n_values": 3}), "structure")


def test_export_rejects_non_integer_row_counts():
    _reject(lambda r: _ed(r).update(rows_protected={"x": "MARKER_SHOULD_NOT_EXPORT"}), "structure")


def test_export_rejects_odd_task_id_and_risk_key_and_score_type():
    _reject(lambda r: r["utility"][0].update(id="H-U2 MARKER value"), "structure")
    _reject(lambda r: r["risk_components"].update({"ed_visits: MARKER\nvalue=1234": 0.1}), "structure")
    _reject(lambda r: r["utility"][0].update(score="1.0"), "not_scored")


def test_export_rejects_odd_dataset_and_table_names():
    _reject(lambda r: r.update(dataset="health; MARKER"), "structure")


# ---- review round 2: sections and benign "not evaluated" ------------------

NO_QI = "no overlapping quasi-identifiers between adversary and protected table"
EXPECTED = {"ed_visits": {"free_text": ["chief_complaint"], "linkage": True}}


def _validate_expecting(report):
    return validate_report(report, scenario="HEALTH-S1", required_tasks=REQUIRED, tables=TABLES,
                           expected_sections=EXPECTED)


def test_benign_linkage_outcome_is_recorded_as_not_applicable_with_its_code():
    report = _passing_report()
    _ed(report)["linkage"]["other_adv"] = {"evaluated": False, "reason": NO_QI}
    summary = _validate(report)
    assert summary["not_applicable"] == [
        {"table": "ed_visits", "section": "linkage", "key": "other_adv", "code": "no_overlapping_qi"}]
    assert "MARKER" not in json.dumps(summary)


def test_unknown_unavailable_reason_is_a_fail():
    def m(r):
        _ed(r)["linkage"]["other_adv"] = {"evaluated": False, "reason": "something new MARKER_SHOULD_NOT_EXPORT"}

    _reject(m, "not_evaluated")


def test_kit_reason_for_missing_row_map_or_truth_is_a_fail():
    def m(r):
        _ed(r)["linkage"]["other_adv"] = {"evaluated": False, "reason": "row map or adversary truth missing"}

    _reject(m, "not_evaluated")


def test_required_free_text_evaluation_that_is_unavailable_is_a_fail_even_for_a_benign_reason():
    report = _passing_report()
    _ed(report)["free_text"]["chief_complaint"] = {"evaluated": False, "reason": "no gold spans in package"}
    with pytest.raises(ScorecardRejected) as caught:
        _validate_expecting(report)
    assert caught.value.reason == "required_not_evaluated"


def test_benign_free_text_outcome_for_a_column_not_required_is_not_applicable():
    report = _passing_report()
    _ed(report)["free_text"]["other_text"] = {"evaluated": False, "reason": "no gold spans in package"}
    summary = _validate(report)
    assert summary["not_applicable"][0]["code"] == "no_gold_spans"


@pytest.mark.parametrize("section", ["regex_residuals", "direct_identifiers_retained"])
def test_deleted_baseline_section_is_a_fail(section):
    _reject(lambda r: _ed(r).pop(section), "missing_section")


def test_deleted_required_free_text_section_is_a_fail():
    report = _passing_report()
    del _ed(report)["free_text"]
    with pytest.raises(ScorecardRejected) as caught:
        _validate_expecting(report)
    assert caught.value.reason == "missing_section"


def test_free_text_section_missing_a_required_column_is_a_fail():
    report = _passing_report()
    _ed(report)["free_text"] = {"other": {"evaluated": True, "n_values": 3}}
    with pytest.raises(ScorecardRejected) as caught:
        _validate_expecting(report)
    assert caught.value.reason == "missing_section"


def test_deleted_required_linkage_section_is_a_fail():
    report = _passing_report()
    del _ed(report)["linkage"]
    with pytest.raises(ScorecardRejected) as caught:
        _validate_expecting(report)
    assert caught.value.reason == "missing_section"


def test_complete_report_passes_with_expected_sections():
    assert _validate_expecting(_passing_report())["not_applicable"] == []


