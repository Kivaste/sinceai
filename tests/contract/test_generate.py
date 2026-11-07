"""Release contract generator: withheld absence, derivations, forms, digest."""

from __future__ import annotations

import hashlib
import json

import pytest

from pets_release.contract import (
    ContractError,
    canonical_bytes,
    digest,
    generate,
    load_forms,
)
from pets_release.contract.forms import MONTH_HOUR_FORM, TOKEN_FORM


def _policy(tables: dict, scenario: str = "HEALTH-S1") -> dict:
    return {"scenario": scenario, "tables": tables}


def _col(**flags) -> dict:
    return flags


def _entry(table: str, column: str, rung: str, params: dict | None = None) -> dict:
    return {
        "table": table,
        "column": column,
        "rung": rung,
        "params": {} if params is None else params,
        "floor": "withheld" if rung == "withheld" else rung,
        "reason": "test",
        "source": "hand",
    }


FORMS = {
    "identifier.pseudonym": TOKEN_FORM,
    "timestamp.month_hour": MONTH_HOUR_FORM,
    "category.exact": r"^[^\r\n]+$",
    "age.band10": r"^(?:0-9|90\+)$",
}


def test_withheld_column_and_table_are_absent() -> None:
    policy = _policy({
        "ed_visits": {"columns": {
            "sex": _col(qi=True),
            "chief_complaint": _col(),
            "postcode": _col(),
        }},
        "clinical_notes": {"withheld": True, "columns": {
            "note_text": _col(),
            "visit_id": _col(),
        }},
    })
    plan = [
        _entry("ed_visits", "sex", "category.exact"),
        _entry("ed_visits", "chief_complaint", "withheld"),
        _entry("ed_visits", "postcode", "withheld"),
        _entry("clinical_notes", "note_text", "withheld"),
        _entry("clinical_notes", "visit_id", "withheld"),
    ]
    contract = generate(policy, plan, forms=FORMS)
    files = contract["files"]
    assert set(files) == {"ed_visits.csv"}
    assert set(files["ed_visits.csv"]["columns"]) == {"sex"}
    blob = canonical_bytes(contract).decode("utf-8")
    for absent in ("chief_complaint", "postcode", "clinical_notes", "note_text"):
        assert absent not in blob
    assert contract["qi"] == [{"table": "ed_visits", "column": "sex", "derived_from": "sex"}]
    assert contract["tokens"] == []


def test_derived_column_uses_release_name_and_source_derivation() -> None:
    policy = _policy({
        "ed_visits": {"columns": {
            "date_of_birth": _col(release_name="age_band", qi=True, required=True),
            "visit_id": _col(required=True, token_scope="release"),
        }},
    })
    plan = [
        _entry("ed_visits", "date_of_birth", "age.band10", {"width": 10, "top": 90}),
        _entry("ed_visits", "visit_id", "identifier.pseudonym"),
    ]
    contract = generate(policy, plan, forms=FORMS)
    columns = contract["files"]["ed_visits.csv"]["columns"]
    assert "date_of_birth" not in columns
    assert "age_band" in columns
    assert columns["age_band"]["form"] == FORMS["age.band10"]
    assert columns["age_band"]["params"]["derived_from"] == "date_of_birth"
    assert columns["age_band"]["params"]["rung"] == "age.band10"
    assert columns["age_band"]["params"]["width"] == 10
    assert contract["files"]["ed_visits.csv"]["required"] == ["age_band", "visit_id"]
    assert contract["qi"] == [
        {"table": "ed_visits", "column": "age_band", "derived_from": "date_of_birth"},
    ]


def test_join_derived_qi_present_only_when_released() -> None:
    def policy(qi_flags: dict) -> dict:
        return _policy({
            "lab_results": {"columns": {"sampled_ts": _col(**qi_flags), "visit_id": _col()}},
        })

    released = generate(
        policy({"qi": True, "derived_from": "join_ed_visits_visit_id"}),
        [_entry("lab_results", "sampled_ts", "category.exact"), _entry("lab_results", "visit_id", "category.exact")],
        forms=FORMS,
    )
    assert released["qi"] == [{
        "table": "lab_results", "column": "sampled_ts", "derived_from": "join_ed_visits_visit_id",
    }]
    assert released["files"]["lab_results.csv"]["columns"]["sampled_ts"]["params"]["derived_from"] == (
        "join_ed_visits_visit_id"
    )

    withheld = generate(
        policy({"qi": True, "derived_from": "join_ed_visits_visit_id"}),
        [_entry("lab_results", "sampled_ts", "withheld"), _entry("lab_results", "visit_id", "category.exact")],
        forms=FORMS,
    )
    assert withheld["qi"] == []
    assert "sampled_ts" not in canonical_bytes(withheld).decode("utf-8")


def test_missing_form_rejected_at_generation() -> None:
    policy = _policy({"ed_visits": {"columns": {"sex": _col()}}})
    plan = [_entry("ed_visits", "sex", "category.exact")]
    with pytest.raises(ContractError, match="sex: form missing"):
        generate(policy, plan, forms={})
    with pytest.raises(ContractError, match="sex: form missing"):
        generate(policy, plan, forms={"category.exact": ""})
    with pytest.raises(ContractError, match="sex: form missing"):
        generate(policy, plan, forms={"category.exact": "   "})


def test_required_column_withheld_rejected() -> None:
    policy = _policy({"ed_visits": {"columns": {"triage": _col(required=True)}}})
    with pytest.raises(ContractError, match="ed_visits.triage: required column withheld"):
        generate(policy, [_entry("ed_visits", "triage", "withheld")], forms=FORMS)


def test_token_columns_carry_scope_and_missing_scope_rejected() -> None:
    policy = _policy({
        "ed_visits": {"columns": {"visit_id": _col(token_scope="release", required=True)}},
        "turns": {"columns": {"conversation_id": _col(token_scope="conversation")}},
    })
    plan = [
        _entry("ed_visits", "visit_id", "identifier.pseudonym"),
        _entry("turns", "conversation_id", "identifier.pseudonym"),
    ]
    contract = generate(policy, plan, forms=FORMS)
    assert contract["tokens"] == [
        {"table": "ed_visits", "column": "visit_id", "scope": "release"},
        {"table": "turns", "column": "conversation_id", "scope": "conversation"},
    ]
    assert contract["files"]["ed_visits.csv"]["columns"]["visit_id"]["form"] == TOKEN_FORM

    bare = _policy({"ed_visits": {"columns": {"visit_id": _col()}}})
    with pytest.raises(ContractError, match="visit_id: token scope missing"):
        generate(bare, [_entry("ed_visits", "visit_id", "identifier.pseudonym")], forms=FORMS)

    bad = _policy({"ed_visits": {"columns": {"visit_id": _col(token_scope="global")}}})
    with pytest.raises(ContractError, match="token scope"):
        generate(bad, [_entry("ed_visits", "visit_id", "identifier.pseudonym")], forms=FORMS)


def test_digest_is_canonical_and_stable_across_runs() -> None:
    policy = _policy({"ed_visits": {"columns": {
        "sex": _col(qi=True),
        "visit_id": _col(token_scope="release"),
    }}})
    plan = [
        _entry("ed_visits", "visit_id", "identifier.pseudonym", {"domain": "visit"}),
        _entry("ed_visits", "sex", "category.exact"),
    ]
    shuffled = list(reversed(plan))
    first = generate(policy, plan, forms=FORMS)
    second = generate(policy, shuffled, forms=FORMS)
    assert canonical_bytes(first) == canonical_bytes(second)
    assert digest(first) == digest(second)
    assert digest(first) == hashlib.sha256(canonical_bytes(first)).hexdigest()
    assert len(digest(first)) == 64
    raw = canonical_bytes({"b": 1, "a": [2, 1]})
    assert raw == b'{"a":[2,1],"b":1}'
    with pytest.raises(ValueError):
        canonical_bytes({"n": float("nan")})


def test_digest_rejects_unknown_contract_key() -> None:
    policy = _policy({"ed_visits": {"columns": {"sex": _col()}}})
    contract = generate(policy, [_entry("ed_visits", "sex", "category.exact")], forms=FORMS)
    planted = {**contract, "pass": True}
    with pytest.raises(ContractError, match="unknown key"):
        digest(planted)
    planted_col = json.loads(canonical_bytes(contract))
    planted_col["files"]["ed_visits.csv"]["columns"]["sex"]["extra"] = "x"
    with pytest.raises(ContractError, match="unknown key"):
        digest(planted_col)


def test_unknown_plan_key_rejected() -> None:
    policy = _policy({"ed_visits": {"columns": {"sex": _col()}}})
    entry = _entry("ed_visits", "sex", "category.exact")
    entry["note"] = "planted"
    with pytest.raises(ContractError, match="unknown key"):
        generate(policy, [entry], forms=FORMS)


def test_dotted_derivation_rejected_so_manifest_name_token_holds() -> None:
    policy = _policy({"lab_results": {"columns": {
        "sampled_ts": _col(qi=True, derived_from="ed_visits.visit_id"),
        "visit_id": _col(),
    }}})
    plan = [
        _entry("lab_results", "sampled_ts", "category.exact"),
        _entry("lab_results", "visit_id", "category.exact"),
    ]
    with pytest.raises(ContractError, match="derived_from"):
        generate(policy, plan, forms=FORMS)


def test_load_forms_uses_ladders_table_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    fake = types.ModuleType("pets_release.ladders")
    fake.RUNG_FORMS = {"from_sibling": r"^sibling$"}
    monkeypatch.setitem(sys.modules, "pets_release.ladders", fake)
    assert load_forms()["from_sibling"] == r"^sibling$"
    assert "identifier.pseudonym" not in load_forms()


def test_load_forms_fallback_pins_month_hour_regex() -> None:
    forms = load_forms()
    assert forms["timestamp.month_hour"] == MONTH_HOUR_FORM
    assert forms["identifier.pseudonym"] == TOKEN_FORM


def test_digest_uses_manifest_digest_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    fake = types.ModuleType("pets_release.manifest")
    fake.canonical_digest = lambda _obj: "ab" * 32
    monkeypatch.setitem(sys.modules, "pets_release.manifest", fake)
    policy = _policy({"ed_visits": {"columns": {"sex": _col()}}})
    contract = generate(policy, [_entry("ed_visits", "sex", "category.exact")], forms=FORMS)
    assert digest(contract) == "ab" * 32


def test_released_column_in_withheld_table_rejected() -> None:
    policy = _policy({"clinical_notes": {"withheld": True, "columns": {"note_text": _col()}}})
    with pytest.raises(ContractError, match="released in withheld table"):
        generate(policy, [_entry("clinical_notes", "note_text", "category.exact")], forms=FORMS)


def test_digest_rejects_unsorted_qi() -> None:
    policy = _policy({"ed_visits": {"columns": {"sex": _col(qi=True), "municipality": _col(qi=True)}}})
    plan = [
        _entry("ed_visits", "municipality", "category.exact"),
        _entry("ed_visits", "sex", "category.exact"),
    ]
    contract = generate(policy, plan, forms=FORMS)
    contract["qi"].reverse()
    with pytest.raises(ContractError, match="unsorted"):
        digest(contract)
