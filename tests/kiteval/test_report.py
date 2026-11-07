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
