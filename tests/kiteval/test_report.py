"""Scorecard report gate: a missing task, an error status, or a zero denominator is a fail."""

import json

import pytest

from pets_release.kiteval.report import ScorecardRejected
from pets_release.kiteval.report import validate_report as _production_validate_report

# #110: every released table's expectation names the catalogued QIs it keeps; the fixture's k result below
# was computed on this one. Tests that give their own ed_visits expectation still get it unless they set it.
K_EXPECTED = {"quasi_identifiers": ["municipality"]}


def validate_report(report, *, expected_sections=None, **kw):
    """The production gate, with the fixture's QI derivation added to ed_visits."""
    exp = dict(expected_sections or {})
    exp["ed_visits"] = {**K_EXPECTED, **exp.get("ed_visits", {})}
    return _production_validate_report(report, expected_sections=exp, **kw)


REQUIRED = ("H-U2", "H-U4")
TABLES = {"ed_visits": 4, "lab_results": 3}  # original table -> original rows, as the adapter read them
RELEASED = {"ed_visits": 4}  # protected table really in the release -> protected rows


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
                "k_anonymity": {"qis": ["municipality"], "n": 4, "min_k": 2, "share_below": {"k<5": 0.5}},
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
        tables=TABLES, released=RELEASED,
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


def test_exported_risks_are_ordered_by_key_whatever_order_the_kit_wrote_them():
    report = _passing_report()
    unsorted = {"records with k<5": 0.5, "direct identifiers retained": 0.25}  # kit order: not sorted by key
    assert list(unsorted) != sorted(unsorted)
    report["tables"]["ed_visits"]["risks"] = dict(unsorted)
    report["risk_components"] = {f"ed_visits: {k}": v for k, v in unsorted.items()}
    exported = list(_validate(report)["risks"])
    assert exported == ["ed_visits: direct identifiers retained", "ed_visits: records with k<5"]


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
EXPECTED = {"ed_visits": {"free_text": ["chief_complaint"], "linkage": {"attacks": ["news_clips_health"]}}}


def _validate_expecting(report):
    return validate_report(report, scenario="HEALTH-S1", required_tasks=REQUIRED, tables=TABLES, released=RELEASED,
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





# ---- review round 3: linkage coverage and trajectories ----------------------


def _expecting(report, expected):
    return validate_report(report, scenario="HEALTH-S1", required_tasks=REQUIRED, tables=TABLES, released=RELEASED,
                           expected_sections={"ed_visits": expected})


def _rejected(report, expected, reason):
    with pytest.raises(ScorecardRejected) as caught:
        _expecting(report, expected)
    assert caught.value.reason == reason


def test_empty_linkage_dict_is_a_fail_when_attacks_are_expected():
    report = _passing_report()
    _ed(report)["linkage"] = {}
    _rejected(report, {"linkage": {"attacks": ["news_clips_health"]}}, "missing_section")


def test_linkage_missing_an_expected_attack_is_a_fail():
    _rejected(_passing_report(), {"linkage": {"attacks": ["news_clips_health", "public_directory"]}},
              "missing_section")


def test_linkage_with_no_expected_attacks_needs_the_kits_no_attack_spec_note():
    report = _passing_report()
    _ed(report)["linkage"] = {}
    _rejected(report, {"linkage": {"attacks": []}}, "missing_section")
    _ed(report)["linkage"] = {"note": "no attack spec targets this table (metadata/attack_specs.json)"}
    summary = _expecting(report, {"linkage": {"attacks": []}})
    assert summary["not_applicable"][0]["code"] == "no_attack_spec"


TRAJ = {"trajectories": {"card_id": {"time": "ts", "location": ["stop_id"]}}}


def _traj(report, result):
    _ed(report)["trajectory_unicity"] = {"card_id": result}


def test_trajectory_no_usable_points_is_a_fail_it_may_be_unparseable_timestamps():
    report = _passing_report()
    _traj(report, {"evaluated": False, "reason": "no usable points"})
    _rejected(report, {**TRAJ, "columns": ["card_id", "ts", "stop_id"]}, "not_evaluated")


def test_trajectory_time_missing_reason_needs_proof_the_column_is_absent():
    report = _passing_report()
    _traj(report, {"evaluated": False, "reason": "user or time column missing"})
    _rejected(report, {**TRAJ, "columns": ["card_id", "ts", "stop_id"]}, "not_evaluated")
    summary = _expecting(report, {**TRAJ, "columns": ["card_id", "stop_id"]})
    assert summary["not_applicable"] == [
        {"table": "ed_visits", "section": "trajectory_unicity", "key": "card_id", "code": "trajectory_time_removed"}]


def test_trajectory_location_missing_reason_needs_every_location_column_absent():
    report = _passing_report()
    _traj(report, {"evaluated": False, "reason": "no location column"})
    _rejected(report, {**TRAJ, "columns": ["card_id", "ts", "stop_id"]}, "not_evaluated")
    summary = _expecting(report, {**TRAJ, "columns": ["card_id", "ts"]})
    assert summary["not_applicable"][0]["code"] == "trajectory_location_removed"


def test_trajectory_with_zero_users_tested_is_a_zero_denominator_fail():
    report = _passing_report()
    _traj(report, {"evaluated": True, "unicity": 0.0, "n_users_tested": 0, "note": "no user has points"})
    _rejected(report, {**TRAJ, "columns": ["card_id", "ts", "stop_id"]}, "zero_denominator")


def test_trajectory_with_users_tested_passes():
    report = _passing_report()
    _traj(report, {"evaluated": True, "unicity": 0.2, "n_users_tested": 50})
    assert _expecting(report, {**TRAJ, "columns": ["card_id", "ts", "stop_id"]})["not_applicable"] == []


def test_trajectory_user_removed_is_accepted_only_when_the_column_is_really_absent():
    report = _passing_report()
    _traj(report, {"evaluated": True, "unicity": 0.0, "note": "card_id removed: traces cannot be linked"})
    _rejected(report, {**TRAJ, "columns": ["card_id", "ts", "stop_id"]}, "structure")
    summary = _expecting(report, {**TRAJ, "columns": ["ts", "stop_id"]})
    assert summary["not_applicable"][0]["code"] == "trajectory_user_removed"


def test_missing_expected_trajectory_section_is_a_fail():
    _rejected(_passing_report(), {**TRAJ, "columns": ["card_id", "ts", "stop_id"]}, "missing_section")


# ---- review round 4: every result record carries an explicit evaluated flag --

_COLS = {**TRAJ, "columns": ["card_id", "ts", "stop_id"]}
SECTION_SLOTS = [
    ("free_text", "chief_complaint"),
    ("linkage", "news_clips_health"),
    ("trajectory_unicity", "card_id"),
    ("hash_attack", "patient_hash"),
]
BAD_RECORDS = [{}, {"n_values": 3, "n_targets_in_data": 3, "n_users_tested": 3, "n_hashes": 3},
               {"evaluated": "yes"}, {"evaluated": None}, {"evaluated": 1}]


def _with_record(section, key, record):
    report = _passing_report()
    _ed(report)["trajectory_unicity"] = {"card_id": GOOD["trajectory_unicity"]}  # expected by _COLS
    _ed(report).setdefault(section, {})[key] = record
    return report


@pytest.mark.parametrize(("section", "key"), SECTION_SLOTS)
@pytest.mark.parametrize("record", BAD_RECORDS)
def test_result_record_without_an_explicit_evaluated_bool_is_a_fail(section, key, record):
    _rejected(_with_record(section, key, record), _COLS, "structure")


GOOD = {
    "free_text": {"evaluated": True, "n_values": 3, "identifying_leakage_rate": 0.0},
    "linkage": {"evaluated": True, "n_targets_in_data": 3, "reidentification_rate": 0.0},
    "trajectory_unicity": {"evaluated": True, "unicity": 0.1, "n_users_tested": 3},
    "hash_attack": {"evaluated": True, "n_hashes": 3, "share_values_reversed": 0.0},
}


@pytest.mark.parametrize(("section", "key"), SECTION_SLOTS)
def test_complete_record_passes_in_every_section(section, key):
    _expecting(_with_record(section, key, GOOD[section]), _COLS)


@pytest.mark.parametrize(("section", "key"), SECTION_SLOTS)
def test_evaluated_record_with_zero_denominator_is_a_fail_in_every_section(section, key):
    field = {"free_text": "n_values", "linkage": "n_targets_in_data", "trajectory_unicity": "n_users_tested",
             "hash_attack": "n_hashes"}[section]
    _rejected(_with_record(section, key, {**GOOD[section], field: 0}), _COLS, "zero_denominator")


@pytest.mark.parametrize(("section", "key"), SECTION_SLOTS)
def test_evaluated_record_without_its_denominator_is_a_fail_in_every_section(section, key):
    field = {"free_text": "n_values", "linkage": "n_targets_in_data", "trajectory_unicity": "n_users_tested",
             "hash_attack": "n_hashes"}[section]
    record = {k: v for k, v in GOOD[section].items() if k != field}
    with pytest.raises(ScorecardRejected) as caught:
        _expecting(_with_record(section, key, record), _COLS)
    assert caught.value.reason in {"structure", "zero_denominator"}


@pytest.mark.parametrize(("section", "key"), SECTION_SLOTS)
def test_unavailable_record_with_unknown_reason_is_a_fail_in_every_section(section, key):
    record = {"evaluated": False, "reason": "unlisted MARKER_SHOULD_NOT_EXPORT"}
    _rejected(_with_record(section, key, record), _COLS, "not_evaluated")


def test_expected_attack_given_as_empty_dict_is_a_fail():
    report = _passing_report()
    _ed(report)["linkage"]["public_directory"] = {}
    _rejected(report, {"linkage": {"attacks": ["news_clips_health", "public_directory"]}}, "structure")



# ---- follow-up #48: no-targets proof, l-diversity, synthetic records -----------

NO_COLS = {"evaluated": True, "qis_used": [], "reidentification_rate": 0.0, "n_targets_in_data": None,
           "note": "every attacker column this attack needs was removed from the release"}


def test_no_targets_linkage_needs_proof_the_attack_columns_are_absent():
    report = _passing_report()
    _ed(report)["linkage"]["news_clips_health"] = dict(NO_COLS)
    _rejected(report, {"linkage": {"attacks": ["news_clips_health"]}}, "structure")
    _rejected(report, {"linkage": {"attacks": ["news_clips_health"], "no_attack_columns": []}}, "structure")
    _rejected(report, {"linkage": {"attacks": ["news_clips_health"], "no_attack_columns": ["other"]}}, "structure")
    _expecting(report, {"linkage": {"attacks": ["news_clips_health"], "no_attack_columns": ["news_clips_health"]}})


def test_no_targets_with_qis_used_is_a_fail_even_with_proof():
    report = _passing_report()
    _ed(report)["linkage"]["news_clips_health"] = dict(NO_COLS, qis_used=[{"kind": "x"}])
    _rejected(report, {"linkage": {"attacks": ["news_clips_health"], "no_attack_columns": ["news_clips_health"]}},
              "structure")


L_DIV = {"evaluated": True, "sensitive": "s", "qis": ["q"], "n_classes": 3, "min_distinct_l": 1}
DCR = {"evaluated": True, "columns": ["q"], "n_synthetic": 3}
MIA = {"evaluated": True, "columns": ["q"], "n_each": 3, "auc": 0.5}


def _extra(report, section, record):
    _ed(report)[section] = record
    return report


EXTRA_SLOTS = [("l_diversity", None, L_DIV, "n_classes"), ("synthetic", "dcr", DCR, "n_synthetic"),
               ("synthetic", "membership_inference", MIA, "n_each")]


def _slot(section, part, record):
    return {part: record} if part else record


@pytest.mark.parametrize(("section", "part", "good", "field"), EXTRA_SLOTS)
def test_l_diversity_and_synthetic_records_pass_when_complete(section, part, good, field):
    _expecting(_extra(_passing_report(), section, _slot(section, part, good)), {})


@pytest.mark.parametrize(("section", "part", "good", "field"), EXTRA_SLOTS)
@pytest.mark.parametrize("bad", [{}, {"evaluated": "yes"}, {"evaluated": None}])
def test_l_diversity_and_synthetic_need_explicit_evaluated(section, part, good, field, bad):
    _rejected(_extra(_passing_report(), section, _slot(section, part, bad)), {}, "structure")


@pytest.mark.parametrize(("section", "part", "good", "field"), EXTRA_SLOTS)
@pytest.mark.parametrize("value", [0, None, float("nan"), -1])
def test_l_diversity_and_synthetic_need_a_positive_denominator(section, part, good, field, value):
    record = {k: v for k, v in good.items() if k != field}
    if value is not None:
        record[field] = value
    _rejected(_extra(_passing_report(), section, _slot(section, part, record)), {}, "zero_denominator")


def test_synthetic_section_must_be_an_object():
    _rejected(_extra(_passing_report(), "synthetic", [1]), {}, "structure")


# ---- must-fix #64: the report's table status and counts must match the real release ----


def _validate_against(report, *, tables=TABLES, released=RELEASED, expected=None):
    return validate_report(report, scenario="HEALTH-S1", required_tasks=REQUIRED, tables=tables,
                           released=released, expected_sections=expected)


def _withheld_ed(report):
    report["tables"]["ed_visits"] = {"table": "ed_visits", "status": "withheld", "rows_original": 4}
    report["risk_components"] = {}


def test_released_table_reported_as_withheld_is_a_fail():
    """The H7 reproduction: scored H-U2, ed_visits marked withheld although it is in the release."""
    report = _passing_report()
    _withheld_ed(report)
    with pytest.raises(ScorecardRejected) as caught:
        _validate_against(report, expected={"ed_visits": {"columns": ["arrival_ts", "triage"]}})
    assert caught.value.reason == "status_mismatch"


def test_withheld_table_reported_as_released_is_a_fail():
    report = _passing_report()
    lab = dict(_ed(report), table="lab_results", rows_original=3)
    report["tables"]["lab_results"] = lab
    report["risk_components"]["lab_results: records with k<5"] = 0.5
    _rejected_for(report, "status_mismatch")


def _rejected_for(report, reason, **kw):
    with pytest.raises(ScorecardRejected) as caught:
        _validate_against(report, **kw)
    assert caught.value.reason == reason


def test_protected_row_count_must_match_the_release():
    _rejected_for(_passing_report(), "row_count_mismatch", released={"ed_visits": 5})


def test_original_row_count_must_match_the_original_tables():
    _rejected_for(_passing_report(), "row_count_mismatch", tables={"ed_visits": 4, "lab_results": 9})
    _rejected_for(_passing_report(), "row_count_mismatch", tables={"ed_visits": 7, "lab_results": 3})


def test_report_table_the_original_does_not_have_is_a_fail():
    report = _passing_report()
    report["tables"]["ghost"] = {"table": "ghost", "status": "withheld", "rows_original": 1}
    _rejected_for(report, "unknown_table")


def test_released_table_the_original_does_not_have_is_a_fail():
    _rejected_for(_passing_report(), "unknown_table", released={"ed_visits": 4, "ghost": 1})


def test_a_release_with_no_released_table_is_a_fail_not_privacy_one():
    report = _passing_report()
    _withheld_ed(report)
    report["summary"]["privacy"] = 1.0
    _rejected_for(report, "no_released_table", released={})


def test_empty_risk_components_are_not_proof_for_a_released_table():
    report = _passing_report()
    report["risk_components"] = {}
    _rejected_for(report, "missing_section")


def test_released_table_with_empty_risks_is_a_fail():
    report = _passing_report()
    _ed(report)["risks"] = {}
    report["risk_components"] = {}
    _rejected_for(report, "missing_section")


def test_risk_components_must_be_exactly_the_released_tables_risks():
    report = _passing_report()
    report["risk_components"]["ed_visits: records with k<5"] = 0.1  # disagrees with the table record
    _rejected_for(report, "risk_mismatch")
    report = _passing_report()
    report["risk_components"]["lab_results: records with k<5"] = 0.0  # a withheld table has no risks
    _rejected_for(report, "risk_mismatch")


@pytest.mark.parametrize("bad", [None, ("ed_visits",), {"ed_visits": "4"}, {"ed_visits": True}, {"ed_visits": -1}])
def test_released_and_tables_must_be_name_to_row_count_maps(bad):
    _rejected_for(_passing_report(), "structure", released=bad)
    _rejected_for(_passing_report(), "structure", tables=bad)


# --- determinism (follow-up #83): exports sorted, independent of the report's dict / list order ---

def test_exported_lists_are_sorted_whatever_the_input_order():
    report = _passing_report()
    report["tables"] = dict(reversed(list(report["tables"].items())))
    report["utility"] = list(reversed(report["utility"]))
    out = _validate(report)
    assert [t["table"] for t in out["tables"]] == sorted(t["table"] for t in out["tables"])
    assert [t["id"] for t in out["tasks"]] == ["H-U2", "H-U4"]


def test_released_table_without_a_qi_derivation_is_a_fail_not_a_skipped_k_check():
    """#110: no expectation for the k evaluation is never read as "nothing to check"."""
    with pytest.raises(ScorecardRejected) as caught:
        _production_validate_report(_passing_report(), scenario="HEALTH-S1", required_tasks=REQUIRED,
                                    tables=TABLES, released=RELEASED, expected_sections=None)
    assert caught.value.reason == "structure"


def test_not_applicable_is_sorted(monkeypatch):
    from pets_release.kiteval import report as mod

    real = mod._check_table

    def check(name, tr, expected, found, **kw):
        res = real(name, tr, expected, found, **kw)
        found.append({"table": name, "section": "linkage", "key": "z", "code": "no_data"})
        found.append({"table": name, "section": "linkage", "key": "a", "code": "no_data"})
        return res

    monkeypatch.setattr(mod, "_check_table", check)
    out = _validate(_passing_report())
    keys = [(i["table"], i["section"], i["key"], i["code"]) for i in out["not_applicable"]]
    assert keys == sorted(keys) and len(keys) >= 4
