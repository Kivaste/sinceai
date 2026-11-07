"""Release contract generator: withheld absence, derivations, forms, digest, and the real gate."""

from __future__ import annotations

import copy
import csv
import re

import pytest

from pets_release.checks import registry
from pets_release.checks.runner import run_checks
from pets_release.contract import ContractError, digest, generate
from pets_release.ladders import CONTRACT_FORMS, LADDERS, RUNG_KIND, VALIDATOR_FORMS, contract_entry
from pets_release.manifest import canonical_bytes, canonical_digest
from pets_release.policy.model import FieldFloor, ScenarioPolicy

REL = {"label": "RECORD_KEY"}


PERSON_TABLES = ("ed_visits", "t", "turns")  # tables the test policy marks as holding a direct identifier


def _policy(floors: dict, qi: tuple = ()) -> ScenarioPolicy:
    return ScenarioPolicy(
        scenario="HEALTH-S1", dataset="d", purpose_checks=(), privacy_targets=(), floors=floors,
        direct_identifiers=tuple((t, "person_ref") for t in PERSON_TABLES), qi=qi, risk_vector=(),
        sacrifices=(), joint_qi_moves=(), linked=(), param_minimums={},
    )


def _finest(rung: str) -> str:
    """Default floor for a test entry: the finest rung of its ladder (so the entry is never finer)."""
    return "withheld" if rung in ("withheld", "no.such.rung") else LADDERS[RUNG_KIND[rung]][0]


def _entry(table: str, column: str, rung: str, params: dict | None = None, floor: str | None = None) -> dict:
    return {
        "table": table, "column": column, "rung": rung, "params": params or {},
        "floor": floor or _finest(rung), "reason": "test", "source": "hand",
    }


def _build(entries: list[dict], qi: tuple = ()):
    floors = {(e["table"], e["column"]): FieldFloor(RUNG_KIND.get(e["floor"], "categorical"), e["floor"], "test") for e in entries}
    return _policy(floors, qi), entries


def test_rung_finer_than_policy_floor_is_rejected() -> None:
    policy, plan = _build([_entry("ed_visits", "patient_hetu", "keep", floor="withheld")])
    with pytest.raises(ContractError, match="patient_hetu: rung finer than floor"):
        generate(policy, plan)
    policy, plan = _build([_entry("ed_visits", "municipality", "geo.full", floor="geo.topn")])
    with pytest.raises(ContractError, match="municipality: rung finer than floor"):
        generate(policy, plan)
    policy, plan = _build([_entry("ed_visits", "municipality", "geo.topn", floor="geo.topn")])
    assert "municipality" in generate(policy, plan)["files"]["ed_visits.csv"]["columns"]
    policy, plan = _build([_entry("ed_visits", "municipality", "withheld", floor="geo.topn")])
    with pytest.raises(ContractError, match="no released files"):
        generate(policy, plan)
    policy, plan = _build([_entry("ed_visits", "municipality", "ts.day", floor="geo.topn")])
    with pytest.raises(ContractError, match="municipality: rung finer than floor"):
        generate(policy, plan)  # a different ladder is not coarser


def test_plan_floor_must_equal_policy_floor() -> None:
    policy, plan = _build([_entry("ed_visits", "municipality", "geo.topn", floor="geo.topn")])
    plan[0]["floor"] = "geo.full"
    with pytest.raises(ContractError, match="municipality: plan floor differs from policy floor"):
        generate(policy, plan)


def test_join_derived_qi_without_join_via_on_non_person_table_rejected() -> None:
    qi = ({"table": "lab_results", "column": "sampled_ts", "derived": "sampled_ts"},)
    policy, plan = _build([_entry("lab_results", "sampled_ts", "ts.month_hour")], qi)
    with pytest.raises(ContractError, match="sampled_ts: join-derived qi needs join_via"):
        generate(policy, plan)


def test_join_via_must_name_an_existing_column() -> None:
    plan = [_entry("lab_results", "sampled_ts", "ts.month_hour"), _entry("ed_visits", "visit_id", "id.pseudonym")]
    for bad in (["ed_visits"], "ed_visits.visit_id", ["ed_visits", "no_col"], ["no_table", "visit_id"], ["a b", "c"]):
        valid = ({"table": "lab_results", "column": "sampled_ts", "derived": "sampled_ts", "join_via": ["ed_visits", "visit_id"]},)
        policy, entries = _build(plan, valid)
        # 09 validates join_via too; bypass it so the generator's own check is what is under test
        object.__setattr__(policy, "qi", ({**valid[0], "join_via": bad},))
        with pytest.raises(ContractError, match="join_via"):
            generate(policy, entries)


def test_qi_and_token_rows_must_name_contract_columns() -> None:
    policy, plan = _build([_entry("t", "a", "keep"), _entry("t", "b", "keep")], (
        {"table": "t", "column": "a", "derived": "a"},))
    contract = generate(policy, plan)
    phantom = copy.deepcopy(contract)
    phantom["qi"].append({"table": "t", "column": "zz", "derived_from": "zz"})  # sorts last
    with pytest.raises(ContractError, match="qi: column not in files"):
        digest(phantom)
    phantom = copy.deepcopy(contract)
    phantom["tokens"] = [{"table": "t", "column": "zz", "scope": "release"}]
    with pytest.raises(ContractError, match="tokens: column not in files"):
        digest(phantom)
    phantom = copy.deepcopy(contract)
    phantom["qi"] = [{"table": "other", "column": "a", "derived_from": "a"}]
    with pytest.raises(ContractError, match="qi: column not in files"):
        digest(phantom)


def test_column_params_come_from_ladder_contract_entry() -> None:
    policy, plan = _build([_entry("t", "a", "keep")])
    body = generate(policy, plan)["files"]["t.csv"]["columns"]["a"]
    assert body["form"] == contract_entry("keep")["form"]
    assert {k: v for k, v in body["params"].items() if k != "rung"} == contract_entry("keep")["params"]

def test_withheld_columns_and_tables_are_absent() -> None:
    policy, plan = _build([
        _entry("ed_visits", "sex", "keep"),
        _entry("ed_visits", "chief_complaint", "withheld"),
        _entry("clinical_notes", "note_text", "withheld"),
        _entry("clinical_notes", "visit_id", "withheld"),
    ])
    contract = generate(policy, plan)
    assert set(contract["files"]) == {"ed_visits.csv"}
    assert set(contract["files"]["ed_visits.csv"]["columns"]) == {"sex"}
    blob = canonical_bytes(contract).decode("utf-8")
    for absent in ("chief_complaint", "clinical_notes", "note_text"):
        assert absent not in blob


def test_derived_column_under_release_name_with_derivation_and_qi() -> None:
    qi = ({"table": "ed_visits", "column": "date_of_birth", "derived": "age_band"},)
    policy, plan = _build([
        _entry("ed_visits", "date_of_birth", "age.band10", {"ref_column": "arrival_ts"}),
        _entry("ed_visits", "sex", "keep"),
    ], qi)
    contract = generate(policy, plan)
    columns = contract["files"]["ed_visits.csv"]["columns"]
    assert "date_of_birth" not in columns
    assert columns["age_band"]["form"] == CONTRACT_FORMS["age.band10"]
    assert columns["age_band"]["params"]["derived_from"] == "date_of_birth"  # not the ref column
    assert contract["qi"] == [{"table": "ed_visits", "column": "age_band", "derived_from": "date_of_birth"}]


def test_qi_listed_only_when_released_and_join_derived_named() -> None:
    qi = ({"table": "lab_results", "column": "sampled_ts", "derived": "sampled_ts", "join_via": ["ed_visits", "visit_id"]},)
    released_policy, released = _build([
        _entry("lab_results", "sampled_ts", "ts.month_hour"),
        _entry("lab_results", "value", "num.exact"),
        _entry("ed_visits", "visit_id", "id.pseudonym"),
    ], qi)
    contract = generate(released_policy, released)
    assert contract["qi"] == [
        {"table": "lab_results", "column": "sampled_ts", "derived_from": "join_ed_visits_visit_id"},
    ]
    withheld_policy, withheld = _build([
        _entry("lab_results", "sampled_ts", "withheld"),
        _entry("lab_results", "value", "num.exact"),
        _entry("ed_visits", "visit_id", "id.pseudonym"),
    ], qi)
    assert generate(withheld_policy, withheld)["qi"] == []


def test_missing_form_rejected_at_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    policy, plan = _build([_entry("t", "c", "no.such.rung")])
    with pytest.raises(ContractError, match="t.c: form missing"):
        generate(policy, plan)
    monkeypatch.setitem(CONTRACT_FORMS, "keep", "")
    policy, plan = _build([_entry("t", "c", "keep")])
    with pytest.raises(ContractError, match="t.c: form invalid"):
        generate(policy, plan)
    monkeypatch.setitem(CONTRACT_FORMS, "keep", r"\d+")  # unanchored regex: the gate rejects it
    with pytest.raises(ContractError, match="t.c: form invalid"):
        generate(policy, plan)


def test_every_ladder_form_is_a_gate_form() -> None:
    for rung, form in CONTRACT_FORMS.items():
        assert form in VALIDATOR_FORMS or (form.startswith("^") and form.endswith("$")), rung
        if form not in VALIDATOR_FORMS:
            re.compile(form)


def test_token_columns_carry_release_scope() -> None:
    policy, plan = _build([
        _entry("ed_visits", "visit_id", "id.pseudonym", REL),
        _entry("turns", "conversation_id", "id.pseudonym"),
    ])
    contract = generate(policy, plan)
    assert contract["tokens"] == [
        {"table": "ed_visits", "column": "visit_id", "scope": "release"},
        {"table": "turns", "column": "conversation_id", "scope": "release"},
    ]
    assert contract["files"]["ed_visits.csv"]["columns"]["visit_id"]["form"] == "hex64"
    policy, plan = _build([_entry("ed_visits", "visit_id", "id.pseudonym", {"scope": "global"})])
    with pytest.raises(ContractError, match="visit_id: token scope"):
        generate(policy, plan)

def test_plan_must_cover_policy_exactly() -> None:
    policy, plan = _build([_entry("t", "a", "keep"), _entry("t", "b", "keep")])
    with pytest.raises(ContractError, match="t.b: plan entry missing"):
        generate(policy, plan[:1])
    with pytest.raises(ContractError, match="t.z: not in policy"):
        generate(policy, [*plan, _entry("t", "z", "keep")])
    with pytest.raises(ContractError, match="t.a: duplicate plan entry"):
        generate(policy, [*plan, _entry("t", "a", "keep")])
    with pytest.raises(ContractError, match="no released files"):
        generate(*_build([_entry("t", "a", "withheld")]))


def test_digest_is_canonical_stable_and_the_manifest_digest() -> None:
    policy, plan = _build([
        _entry("ed_visits", "visit_id", "id.pseudonym", REL),
        _entry("ed_visits", "sex", "keep"),
    ])
    first = generate(policy, plan)
    second = generate(policy, list(reversed(plan)))
    assert canonical_bytes(first) == canonical_bytes(second)
    assert digest(first) == digest(second) == canonical_digest(first)
    assert len(digest(first)) == 64


def test_digest_rejects_unknown_keys_and_unsorted_lists() -> None:
    qi = (
        {"table": "t", "column": "a", "derived": "a"},
        {"table": "t", "column": "b", "derived": "b"},
    )
    policy, plan = _build([_entry("t", "a", "keep"), _entry("t", "b", "keep")], qi)
    contract = generate(policy, plan)
    with pytest.raises(ContractError, match="unknown key"):
        digest({**contract, "pass": True})
    planted = copy.deepcopy(contract)
    planted["files"]["t.csv"]["columns"]["a"]["extra"] = "x"
    with pytest.raises(ContractError, match="unknown key"):
        digest(planted)
    planted = copy.deepcopy(contract)
    planted["qi"].reverse()
    with pytest.raises(ContractError, match="unsorted"):
        digest(planted)


def test_unknown_plan_key_rejected() -> None:
    policy, plan = _build([_entry("t", "a", "keep")])
    plan[0]["note"] = "planted"
    with pytest.raises(ContractError, match="unknown key"):
        generate(policy, plan)


# --- the real gate (ticket 04) over a release built from a generated contract -------------

_SAMPLE = {
    "id.pseudonym": "a" * 64, "keep": "x", "ts.month_hour": "2025-03-01T14:00", "ts.hour": "2025-03-04T14:00",
    "age.band10": "30-39", "icd.3": "J18", "num.exact": "37.5", "geo.full": "Espoo",
}


def _contract_checks():
    return [c for c in registry.all_checks() if c.name.startswith("contract.")]


def _write_release(root, contract, rows: dict) -> None:
    for name, spec in contract["files"].items():
        columns = sorted(spec["columns"])
        with (root / name).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            for row in rows[name]:
                writer.writerow([row[c] for c in columns])


def _synthetic():
    qi = ({"table": "ed_visits", "column": "date_of_birth", "derived": "age_band"},)
    policy, plan = _build([
        _entry("ed_visits", "visit_id", "id.pseudonym", REL),
        _entry("ed_visits", "date_of_birth", "age.band10", {"ref_column": "arrival_ts"}),
        _entry("ed_visits", "arrival_ts", "ts.month_hour"),
        _entry("ed_visits", "icd10_primary", "icd.3"),
        _entry("ed_visits", "temp_c", "num.exact"),
        _entry("ed_visits", "municipality", "geo.full"),
        _entry("ed_visits", "sex", "keep"),
        _entry("ed_visits", "postcode", "withheld"),
    ], qi)
    contract = generate(policy, plan)
    sample = {
        "visit_id": "a" * 64, "age_band": "30-39", "arrival_ts": "2025-03-01T14:00",
        "icd10_primary": "J18", "temp_c": "37.5", "municipality": "Espoo", "sex": "F",
    }
    return contract, {"ed_visits.csv": [dict(sample), {**sample, "visit_id": "b" * 64, "age_band": "90+"}]}


def test_generated_contract_passes_the_gate_contract_checks(tmp_path) -> None:
    contract, rows = _synthetic()
    _write_release(tmp_path, contract, rows)
    result = run_checks(tmp_path, contract, checks=_contract_checks())
    assert {r.check for r in result.records} == {"contract.columns", "contract.files", "contract.forms"}
    assert [(r.check, r.status) for r in result.records if r.status != "pass"] == []
    assert not result.refused


def test_gate_refuses_a_cell_outside_the_generated_form(tmp_path) -> None:
    contract, rows = _synthetic()
    rows["ed_visits.csv"][0]["arrival_ts"] = "2025-03-17T14:30"
    rows["ed_visits.csv"][1]["age_band"] = "1985-02-03"
    _write_release(tmp_path, contract, rows)
    result = run_checks(tmp_path, contract, checks=_contract_checks())
    assert result.refused
    forms = next(r for r in result.records if r.check == "contract.forms")
    assert forms.status == "fail"
    assert {v.column for v in forms.violations} == {"arrival_ts", "age_band"}


def test_gate_refuses_a_withheld_column_in_the_release(tmp_path) -> None:
    contract, rows = _synthetic()
    _write_release(tmp_path, contract, rows)
    path = tmp_path / "ed_visits.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("age_band", "postcode", 1), encoding="utf-8")
    result = run_checks(tmp_path, contract, checks=_contract_checks())
    columns = next(r for r in result.records if r.check == "contract.columns")
    assert columns.status == "fail"
    assert {v.label for v in columns.violations} == {"extraColumn", "missingRequiredColumn"}
