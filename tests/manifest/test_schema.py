"""Closed manifest schema: one red test per failure row.

Rule: a manifest is valid only if every record is closed, every required export assertion is present and is the
literal ``false``, and every assertion is backed by exactly one passing, zero-hit evidence record from its own
named gate check with a non-empty denominator.
"""

import pytest

from pets_release.manifest import (
    ALL_ASSERTIONS,
    ASSERTION_SCOPES,
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


# --- verification scope is pinned per assertion (spec §14, D18) -------------------------------------------------

SPEC_SCOPES = {**{n: "release" for n in LABEL_ASSERTIONS}, "healthInText": "release", "rawTimestamps": "release",
               "rowMaps": "release", "reversibleHashes": "producer", "keyMaterial": "producer",
               "quasiIdentifiersBelowK": "producer"}


def _as_cs(m):
    """Turn the HEALTH-S1 fixture into a valid CS-S1 manifest (k assertion -> healthInText)."""
    m["release"]["scenario"] = "CS-S1"
    m["fitFor"] = [{"scenario": "CS-S1", "reason": "test variant"}]
    m["notFitFor"] = [{"scenario": "HEALTH-S1", "reason": "test variant"}]
    del m["exportAssertions"]["quasiIdentifiersBelowK"]
    old = m["assertionEvidence"].pop("quasiIdentifiersBelowK")["check"]
    ev = {"check": "text.health", "version": "1.0.0", "scope": "release", "status": "pass",
          "denominator": {"unit": "turns", "n": 40}, "hits": 0}
    m["exportAssertions"]["healthInText"] = False
    m["assertionEvidence"]["healthInText"] = ev
    m["gate"]["checks"] = sorted([c for c in m["gate"]["checks"] if c["check"] != old] + [dict(ev)],
                                 key=lambda c: c["check"])
    m["bindings"]["checkVersions"] = {c["check"]: c["version"] for c in m["gate"]["checks"]}
    m["bindings"]["lexiconDigests"] = {"health-lexicon": "a" * 64}
    m["release"]["releaseScopeId"] = _scope_id(m)
    m["contract"].pop("k", None)
    m["contract"]["healthInTextRequired"] = True
    _rebind_contract(m)
    return m


def _rebind_contract(m):
    from pets_release.manifest import canonical_digest

    m["bindings"]["contractDigest"] = canonical_digest(m["contract"])


@pytest.mark.parametrize("value", ["missing", False, None, 0, 1, "true"])
def test_cs_contract_requires_literal_true_health_enforcement(m, value):
    _as_cs(m)
    if value == "missing":
        del m["contract"]["healthInTextRequired"]
    else:
        m["contract"]["healthInTextRequired"] = value
    _rebind_contract(m)
    assert validate_manifest(m)


# --- contract.k: the scenario's k-anonymity target --------------------------------------------------------------

def test_health_fixture_contract_carries_k_5_and_binds_it(m):
    from pets_release.manifest import canonical_digest

    assert m["contract"]["k"] == 5
    assert m["bindings"]["contractDigest"] == canonical_digest(m["contract"])
    assert validate_manifest(m) == []


def test_health_contract_without_k_is_invalid(m):
    del m["contract"]["k"]
    _rebind_contract(m)
    assert "$.contract: required" in validate_manifest(m)


def test_cs_contract_with_k_is_invalid(m):
    m = _as_cs(m)
    m["contract"]["k"] = 5
    _rebind_contract(m)
    assert "$.contract: not" in validate_manifest(m)


@pytest.mark.parametrize("value,code", [
    (1, "minimum"), (0, "minimum"), (-3, "minimum"), (2.5, "type"), ("5", "type"), (True, "type"), (None, "type"),
])
def test_invalid_k_is_invalid(m, value, code):
    m["contract"]["k"] = value
    assert f"$.contract.k: {code}" in validate_manifest(m)


def test_k_2_is_the_smallest_valid_target(m):
    m["contract"]["k"] = 2
    _rebind_contract(m)
    assert validate_manifest(m) == []


def test_changed_k_without_rebinding_digest_is_invalid(m):
    m["contract"]["k"] = 6
    assert "$.bindings.contractDigest: mismatch" in validate_manifest(m)


def test_cs_variant_is_valid(m):
    assert validate_manifest(_as_cs(m)) == []


def test_spec_scope_table_covers_every_assertion():
    assert set(SPEC_SCOPES) == set(ALL_ASSERTIONS)
    assert ASSERTION_SCOPES == SPEC_SCOPES


@pytest.mark.parametrize("name", ALL_ASSERTIONS)
def test_flipping_assertion_scope_with_its_gate_record_is_invalid(m, name):
    if name not in HEALTH:
        m = _as_cs(m)
    ev = m["assertionEvidence"][name]
    assert ev["scope"] == SPEC_SCOPES[name]
    flipped = "release" if ev["scope"] == "producer" else "producer"
    ev["scope"] = flipped
    next(c for c in m["gate"]["checks"] if c["check"] == ev["check"])["scope"] = flipped
    invalid(m, f"$.assertionEvidence.{name}.scope: const")


# --- each assertion is bound to its own registered check (ticket 04 ASSERTION_CHECKS) ---------------------------

def _gate_record(m, check):
    return next(c for c in m["gate"]["checks"] if c["check"] == check)


@pytest.mark.parametrize("name", HEALTH)
def test_evidence_repointed_at_another_gate_check_is_invalid(m, name):
    # Re-point at a gate check that passed with 0 hits (release.file-digests), keeping gate agreement.
    rec = dict(_gate_record(m, "release.file-digests"))
    rec["scope"] = m["assertionEvidence"][name]["scope"]
    _gate_record(m, "release.file-digests")["scope"] = rec["scope"]
    m["assertionEvidence"][name] = rec
    assert f"$.assertionEvidence.{name}.check: const" in validate_manifest(m)


def test_swapped_evidence_is_invalid(m):
    ev = m["assertionEvidence"]
    ev["emails"], ev["phones"] = ev["phones"], ev["emails"]
    errs = validate_manifest(m)
    assert "$.assertionEvidence.emails.check: const" in errs
    assert "$.assertionEvidence.phones.check: const" in errs


@pytest.mark.parametrize("name", ALL_ASSERTIONS)
def test_evidence_with_wrong_denominator_unit_is_invalid(m, name):
    if name not in HEALTH:
        m = _as_cs(m)
    ev = m["assertionEvidence"][name]
    wrong = "rows" if ev["denominator"]["unit"] != "rows" else "cells"
    ev["denominator"]["unit"] = wrong
    _gate_record(m, ev["check"])["denominator"]["unit"] = wrong
    assert f"$.assertionEvidence.{name}.denominator.unit: const" in validate_manifest(m)


# --- releaseScopeId is recomputed from the bound inputs (same derivation as ticket 06) ---------------------------

def _scope_id(m):
    import hashlib
    import json

    payload = {"inputs": m["bindings"]["inputs"], "recipient": m["release"]["recipient"],
               "scenario": m["release"]["scenario"], "toolRevision": m["bindings"]["toolRevision"]}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def test_fixture_release_scope_id_uses_pinned_derivation(m):
    assert m["release"]["releaseScopeId"] == _scope_id(m)


@pytest.mark.parametrize("mutate", [
    lambda m: m["release"].__setitem__("releaseScopeId", "0123456789abcdef"),
    lambda m: m["release"].__setitem__("recipient", "another-recipient"),
    lambda m: m["bindings"].__setitem__("toolRevision", "1" * 40),
    lambda m: m["bindings"]["inputs"].__setitem__("ed_visits", "b" * 64),
])
def test_release_scope_id_mismatch_is_invalid(m, mutate):
    mutate(m)
    assert "$.release.releaseScopeId: mismatch" in validate_manifest(m)


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
    invalid(m, "$.assertionEvidence.emails.check: const")


def test_evidence_check_not_run_by_gate_is_invalid(m):
    m["gate"]["checks"] = [c for c in m["gate"]["checks"] if c["check"] != "rescan.emails"]
    del m["bindings"]["checkVersions"]["rescan.emails"]
    invalid(m, "$.assertionEvidence.emails.check: not-in-gate")


def test_evidence_disagreeing_with_gate_record_is_invalid(m):
    m["assertionEvidence"]["emails"]["denominator"] = {"unit": "cells", "n": 999}
    invalid(m, "$.assertionEvidence.emails: gate-mismatch")


def test_check_version_not_bound_is_invalid(m):
    m["bindings"]["checkVersions"]["rescan.emails"] = "9.9.9"
    invalid(m, "$.bindings.checkVersions: gate-mismatch")


# --- not_applicable gate records (ticket 04 runner): allowed in the gate list, never as evidence ------------------

def _make_not_applicable(rec):
    rec["status"] = "not_applicable"
    rec["denominator"]["n"] = 0
    rec["hits"] = 0


def test_not_applicable_gate_record_for_a_non_assertion_check_is_valid(m):
    _make_not_applicable(_gate_record(m, "release.token-hex64"))
    assert validate_manifest(m) == []


@pytest.mark.parametrize("field,value,code", [
    (("denominator", "n"), 3, "n: const"),
    (("hits",), 1, "hits: const"),
])
def test_not_applicable_gate_record_must_have_zero_denominator_and_hits(m, field, value, code):
    rec = _gate_record(m, "release.token-hex64")
    _make_not_applicable(rec)
    target = rec
    for f in field[:-1]:
        target = target[f]
    target[field[-1]] = value
    invalid(m, code)


def test_pass_gate_record_with_zero_denominator_is_invalid(m):
    _gate_record(m, "release.token-hex64")["denominator"]["n"] = 0
    invalid(m, "n: minimum")


@pytest.mark.parametrize("name", HEALTH)
def test_not_applicable_record_cannot_back_an_assertion(m, name):
    ev = m["assertionEvidence"][name]
    _make_not_applicable(_gate_record(m, ev["check"]))
    # evidence left as "pass": disagrees with the gate record
    assert f"$.assertionEvidence.{name}: gate-mismatch" in validate_manifest(m)
    # evidence copied from the not_applicable gate record: the evidence schema rejects it
    m["assertionEvidence"][name] = {**_gate_record(m, ev["check"]),
                                    "denominator": dict(_gate_record(m, ev["check"])["denominator"])}
    errs = validate_manifest(m)
    assert f"$.assertionEvidence.{name}.status: const" in errs
    assert f"$.assertionEvidence.{name}.denominator.n: minimum" in errs


@pytest.mark.parametrize("status", ["not_run", "error", "fail", None])
def test_gate_check_not_passed_is_invalid(m, status):
    m["gate"]["checks"][0]["status"] = status
    invalid(m, "$.gate.checks[0].status: enum")


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
    # Inside a oneOf (measured.* and residual-risk rate) jsonschema reports at the oneOf node.
    under_one_of = {"$.measured.utility": "$.measured.utility", "$.measured.utility.tasks[0]": "$.measured.utility",
                    "$.measured.search": "$.measured.search", "$.residualRisks[0].rate": "$.residualRisks[0].rate"}
    code = f"{under_one_of[where]}: oneOf" if where in under_one_of else f"{where}: additionalProperties"
    assert code in validate_manifest(m), where


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
    i = next(i for i, f in enumerate(m["fieldJustifications"]) if f["rung"] == "withheld")
    m["fieldJustifications"][i]["outputColumn"] = "x"
    assert f"$.fieldJustifications[{i}].outputColumn: type" in validate_manifest(m)


def test_released_field_marked_withheld_rung_is_invalid(m):
    i = next(i for i, f in enumerate(m["fieldJustifications"]) if f["decision"] == "released")
    m["fieldJustifications"][i]["rung"] = "withheld"
    assert f"$.fieldJustifications[{i}].rung: not" in validate_manifest(m)


# --- CS-S1 binds its lexicon (healthInText is scoped to the bound lexicon version) --------------------------------

def test_cs_manifest_without_lexicon_digest_is_invalid(m):
    m = _as_cs(m)
    m["bindings"]["lexiconDigests"] = {}
    invalid(m, "$.bindings.lexiconDigests: minProperties")


def test_health_manifest_may_bind_no_lexicon(m):
    assert m["bindings"]["lexiconDigests"] == {} and validate_manifest(m) == []


# --- assertion maps are closed even when no scenario rule applies ------------------------------------------------

def test_unknown_assertion_is_rejected_without_a_scenario_rule(m):
    m["release"]["scenario"] = "CS-S9"
    m["exportAssertions"]["directIdentifiers"] = False
    m["assertionEvidence"]["directIdentifiers"] = dict(m["assertionEvidence"]["emails"])
    errs = validate_manifest(m)
    assert "$.exportAssertions: additionalProperties" in errs
    assert "$.assertionEvidence: additionalProperties" in errs


def test_true_assertion_is_rejected_without_a_scenario_rule(m):
    m["release"]["scenario"] = "CS-S9"
    m["exportAssertions"]["emails"] = True
    assert "$.exportAssertions.emails: const" in validate_manifest(m)


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
