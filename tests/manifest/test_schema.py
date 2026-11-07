"""Closed manifest schema: one red test per failure row.

Rule: a manifest is valid only if every record is closed, every required export assertion is present and is the
literal ``false``, and every assertion is backed by exactly one passing, zero-hit evidence record from its own
named gate check with a non-empty denominator.
"""

import pytest

from pets_release.manifest import (
    ALL_ASSERTIONS,
    LABEL_ASSERTIONS,
    not_measured,
    required_assertions,
    validate_manifest,
)

HEALTH = required_assertions("HEALTH-S1")
CS = required_assertions("CS-S1")


def invalid(m, code):
    errs = validate_manifest(m)
    assert errs, "expected the manifest to be invalid"
    assert any(code in e for e in errs), errs
    return errs


# --- the fixture is the green baseline -------------------------------------------------------------------------

def test_fixture_manifest_is_valid(m):
    assert validate_manifest(m) == []


def test_required_assertions_match_the_spec():
    labels = {"nationalIds", "paymentCards", "ibans", "accountNumbers", "emails", "phones", "ipAddresses",
              "deviceIds", "usernames", "propertyIds", "plates", "secrets", "urlsWithTokens"}
    common = labels | {"rawTimestamps", "reversibleHashes", "keyMaterial", "rowMaps"}
    assert set(LABEL_ASSERTIONS) == labels
    assert set(HEALTH) == common | {"quasiIdentifiersBelowK"}
    assert set(CS) == common | {"healthInText"}
    assert set(ALL_ASSERTIONS) == common | {"quasiIdentifiersBelowK", "healthInText"}
    assert "directIdentifiers" not in ALL_ASSERTIONS
    assert list(HEALTH) == sorted(HEALTH)


def test_unknown_scenario_has_no_required_assertions_and_is_invalid(m):
    with pytest.raises(KeyError):
        required_assertions("CS-S9")
    m["release"]["scenario"] = "CS-S9"
    invalid(m, "$.release.scenario: enum")


# --- export assertions: only the literal false --------------------------------------------------------------

@pytest.mark.parametrize("name", HEALTH)
@pytest.mark.parametrize("value", [True, None, 0, "false", [], {}])
def test_assertion_not_literal_false_is_invalid(m, name, value):
    m["exportAssertions"][name] = value
    invalid(m, f"$.exportAssertions.{name}: const")


@pytest.mark.parametrize("name", HEALTH)
def test_missing_assertion_is_invalid(m, name):
    del m["exportAssertions"][name]
    invalid(m, "$.exportAssertions: required")


@pytest.mark.parametrize("name", ["directIdentifiers", "noIdentifiers", "healthInText", "Emails"])
def test_unknown_or_out_of_scenario_assertion_is_invalid(m, name):
    m["exportAssertions"][name] = False
    m["assertionEvidence"][name] = dict(m["assertionEvidence"]["emails"], check=f"x-{name.lower()}")
    invalid(m, "$.exportAssertions: additionalProperties")


def test_cs_scenario_requires_health_in_text_and_forbids_k(m):
    m["release"]["scenario"] = "CS-S1"
    errs = invalid(m, "$.exportAssertions: required")
    assert any("$.exportAssertions: additionalProperties" in e for e in errs)


# --- assertion evidence ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["check", "version", "scope", "status", "denominator", "hits"])
def test_evidence_missing_field_is_invalid(m, field):
    del m["assertionEvidence"]["emails"][field]
    invalid(m, "$.assertionEvidence.emails: required")


@pytest.mark.parametrize("field,value,code", [
    ("scope", "both", "scope: enum"),
    ("scope", None, "scope: enum"),
    ("hits", 1, "hits: const"),
    ("hits", None, "hits: const"),
    ("status", "error", "status: const"),
    ("status", "not_run", "status: const"),
    ("status", "fail", "status: const"),
    ("denominator", {"unit": "cells", "n": 0}, "n: minimum"),
    ("denominator", {"unit": "cells", "n": -1}, "n: minimum"),
    ("denominator", {"unit": "cells", "n": 1.5}, "n: type"),
    ("denominator", {"unit": "bytes", "n": 3}, "unit: enum"),
    ("denominator", {"unit": "cells"}, "denominator: required"),
    ("version", "", "version: pattern"),
    ("check", "", "check: pattern"),
])
def test_evidence_bad_field_is_invalid(m, field, value, code):
    m["assertionEvidence"]["emails"][field] = value
    invalid(m, code)


def test_assertion_without_evidence_is_invalid(m):
    del m["assertionEvidence"]["emails"]
    invalid(m, "$.assertionEvidence: required")


def test_evidence_without_assertion_is_invalid(m):
    m["assertionEvidence"]["directIdentifiers"] = dict(m["assertionEvidence"]["emails"], check="x")
    invalid(m, "$.assertionEvidence: additionalProperties")


def test_two_assertions_sharing_one_check_is_invalid(m):
    m["assertionEvidence"]["emails"] = dict(m["assertionEvidence"]["phones"])
    invalid(m, "$.assertionEvidence.emails.check: shared")


def test_evidence_check_not_run_by_gate_is_invalid(m):
    m["gate"]["checks"] = [c for c in m["gate"]["checks"] if c["check"] != "rescan-email"]
    del m["bindings"]["checkVersions"]["rescan-email"]
    invalid(m, "$.assertionEvidence.emails.check: not-in-gate")


def test_evidence_disagreeing_with_gate_record_is_invalid(m):
    m["assertionEvidence"]["emails"]["denominator"] = {"unit": "cells", "n": 999}
    invalid(m, "$.assertionEvidence.emails: gate-mismatch")


def test_check_version_not_bound_is_invalid(m):
    m["bindings"]["checkVersions"]["rescan-email"] = "9.9.9"
    invalid(m, "$.bindings.checkVersions: gate-mismatch")


def test_gate_check_not_passed_is_invalid(m):
    m["gate"]["checks"][0]["status"] = "not_run"
    invalid(m, "status: const")


# --- closed at every level ---------------------------------------------------------------------------------------

def _paths(m):
    return {
        "$": m,
        "$.release": m["release"],
        "$.bindings": m["bindings"],
        "$.inventory[0]": m["inventory"][0],
        "$.pets[0]": m["pets"][0],
        "$.fieldJustifications[0]": m["fieldJustifications"][0],
        "$.contract": m["contract"],
        "$.contract.files.ed_visits.csv": m["contract"]["files"]["ed_visits.csv"],
        "$.contract.files.ed_visits.csv.columns.sex": m["contract"]["files"]["ed_visits.csv"]["columns"]["sex"],
        "$.contract.qi[0]": m["contract"]["qi"][0],
        "$.contract.tokens[0]": m["contract"]["tokens"][0],
        "$.assertionEvidence.emails": m["assertionEvidence"]["emails"],
        "$.assertionEvidence.emails.denominator": m["assertionEvidence"]["emails"]["denominator"],
        "$.gate": m["gate"],
        "$.gate.checks[0]": m["gate"]["checks"][0],
        "$.measured": m["measured"],
        "$.measured.utility": m["measured"]["utility"],
        "$.measured.utility.tasks[0]": m["measured"]["utility"]["tasks"][0],
        "$.measured.search": m["measured"]["search"],
        "$.residualRisks[0]": m["residualRisks"][0],
        "$.residualRisks[0].rate": m["residualRisks"][0]["rate"],
        "$.fitFor[0]": m["fitFor"][0],
        "$.temporaryState": m["temporaryState"],
        "$.signature": m["signature"],
    }


@pytest.mark.parametrize("where", list(_paths({
    "release": {}, "bindings": {}, "inventory": [{}], "pets": [{}], "fieldJustifications": [{}],
    "contract": {"files": {"ed_visits.csv": {"columns": {"sex": {}}}}, "qi": [{}], "tokens": [{}]},
    "assertionEvidence": {"emails": {"denominator": {}}}, "gate": {"checks": [{}]},
    "measured": {"utility": {"tasks": [{}]}, "search": {}}, "residualRisks": [{"rate": {}}], "fitFor": [{}],
    "temporaryState": {}, "signature": {},
})))
def test_unknown_key_at_any_level_is_invalid(m, where):
    _paths(m)[where]["unexpectedKey"] = False
    errs = validate_manifest(m)
    assert errs, where


@pytest.mark.parametrize("key", ["schemaVersion", "release", "bindings", "inventory", "pets", "fieldJustifications",
                                 "contract", "exportAssertions", "assertionEvidence", "gate", "measured",
                                 "sacrifices", "residualRisks", "fitFor", "notFitFor", "temporaryState",
                                 "signature"])
def test_missing_top_level_key_is_invalid(m, key):
    del m[key]
    invalid(m, "$: required")


@pytest.mark.parametrize("key", ["mappingTablesPersisted", "rowMapsInRelease"])
def test_temporary_state_true_is_invalid(m, key):
    m["temporaryState"][key] = True
    invalid(m, f"$.temporaryState.{key}: const")


# --- measured.*: not-yet-measured is schema-valid ----------------------------------------------------------------

@pytest.mark.parametrize("section", ["utility", "privacy", "search", "baselines", "redaction"])
def test_not_measured_section_is_valid(m, section):
    m["measured"][section] = not_measured("pending measurer")
    assert validate_manifest(m) == []


@pytest.mark.parametrize("section", ["utility", "privacy", "search", "baselines", "redaction"])
def test_measured_section_with_unknown_status_is_invalid(m, section):
    m["measured"][section] = {"status": "pending", "reason": "x"}
    assert validate_manifest(m)


def test_not_measured_needs_a_reason(m):
    m["measured"]["utility"] = {"status": "not_measured"}
    assert validate_manifest(m)


def test_residual_risk_rate_not_measured_is_valid(m):
    m["residualRisks"][0]["rate"] = not_measured("pending attacker")
    assert validate_manifest(m) == []


# --- cross-field and order rules ---------------------------------------------------------------------------------

def test_unsorted_list_is_invalid(m):
    m["inventory"].reverse()
    invalid(m, "$.inventory: order")


def test_duplicate_list_entry_is_invalid(m):
    m["fitFor"].append(dict(m["fitFor"][0]))
    invalid(m, "$.fitFor: order")


def test_bound_files_must_equal_contract_files(m):
    m["bindings"]["files"]["extra.csv"] = "0" * 64
    invalid(m, "$.bindings.files: contract-mismatch")


def test_manifest_cannot_bind_itself_or_non_csv(m):
    m["bindings"]["files"]["privacy_manifest.json"] = "0" * 64
    invalid(m, "$.bindings.files: propertyNames")


def test_withheld_field_with_output_column_is_invalid(m):
    fj = next(f for f in m["fieldJustifications"] if f["rung"] == "withheld")
    fj["outputColumn"] = "x"
    invalid(m, "$.fieldJustifications[")


def test_bad_digest_shape_is_invalid(m):
    m["bindings"]["contractDigest"] = "abc"
    invalid(m, "$.bindings.contractDigest: pattern")


def test_signature_alg_is_pinned(m):
    m["signature"]["alg"] = "none"
    invalid(m, "$.signature.alg: const")


# --- content-free error output -----------------------------------------------------------------------------------

def test_errors_never_echo_instance_values(m):
    marker = "MARKER-VALUE-4111111111111111"
    m["release"]["recipient"] = 12345
    m["fitFor"][0]["reason"] = {"x": marker}
    m["exportAssertions"]["emails"] = marker
    m["unexpected-" + "k"] = marker
    errs = validate_manifest(m)
    assert errs
    joined = "\n".join(errs)
    assert marker not in joined and "12345" not in joined and "4111" not in joined


def test_non_object_manifest_is_invalid():
    assert validate_manifest([]) and validate_manifest(None) and validate_manifest("x")
