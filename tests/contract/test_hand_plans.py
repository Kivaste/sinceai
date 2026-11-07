"""Contracts for ticket 09's real hand plans, through the production generator and CLI."""

from __future__ import annotations

import dataclasses
import subprocess
import sys

import pytest

from pets_release.contract import ContractError, digest, generate
from pets_release.contract import __main__ as cli
from pets_release.policy import get_policy, hand_plan


@pytest.mark.parametrize("scenario", ["HEALTH-S1", "CS-S1"])
def test_hand_plan_contract_matches_plan(scenario: str) -> None:
    policy, plan = get_policy(scenario), hand_plan(scenario)
    contract = generate(policy, plan)
    assert digest(contract) == digest(generate(policy, list(reversed(plan))))
    released = {(e["table"], e["column"]) for e in plan if e["rung"] != "withheld"}
    in_contract = {
        (name[: -len(".csv")], col)
        for name, spec in contract["files"].items()
        for col in spec["columns"]
    }
    assert len(in_contract) == len(released)
    withheld_tables = {t for t, _ in policy.floors} - {t for t, _ in released}
    assert not withheld_tables & {n[: -len(".csv")] for n in contract["files"]}
    for row in contract["tokens"]:
        assert contract["files"][f"{row['table']}.csv"]["columns"][row["column"]]["form"] == "hex64"


def test_health_contract_has_age_band_derivation_and_released_qis() -> None:
    contract = generate(get_policy("HEALTH-S1"), hand_plan("HEALTH-S1"))
    columns = contract["files"]["ed_visits.csv"]["columns"]
    assert "date_of_birth" not in columns
    assert columns["age_band"]["params"]["derived_from"] == "date_of_birth"
    assert {"table": "ed_visits", "column": "age_band", "derived_from": "date_of_birth"} in contract["qi"]
    assert not [r for r in contract["qi"] if r["table"] == "lab_results"]  # sampled_ts withheld


def test_cli_prints_both_contracts(tmp_path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "pets_release.contract", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "scenario HEALTH-S1" in done.stdout and "scenario CS-S1" in done.stdout
    assert (tmp_path / "HEALTH-S1.contract.json").is_file() and (tmp_path / "contracts.txt").is_file()


def test_cli_writes_nothing_when_a_scenario_is_rejected(tmp_path, monkeypatch) -> None:
    real = cli.generate

    def failing(policy, plan):
        if policy.scenario == "CS-S1":
            raise ContractError("forced")
        return real(policy, plan)

    monkeypatch.setattr(cli, "generate", failing)
    assert cli.main([str(tmp_path)]) == 1
    assert list(tmp_path.iterdir()) == []


def _with_sampled_ts_released(join_via):
    """Real 09 policy and plan, sampled_ts released, the QI row's join_via replaced (None removes it)."""
    policy, plan = get_policy("HEALTH-S1"), hand_plan("HEALTH-S1")
    for entry in plan:
        if (entry["table"], entry["column"]) == ("lab_results", "sampled_ts"):
            entry["rung"], entry["params"] = "ts.month_hour", {}
    qi = []
    for row in policy.qi:
        if row["column"] == "sampled_ts":
            row = {k: v for k, v in row.items() if k != "join_via"}
            if join_via is not None:
                row["join_via"] = join_via
        qi.append(row)
    return dataclasses.replace(policy, qi=tuple(qi)), plan


def test_released_join_derived_qi_carries_join_derivation() -> None:
    policy, plan = _with_sampled_ts_released(["ed_visits", "visit_id"])
    row = next(r for r in generate(policy, plan)["qi"] if r["column"] == "sampled_ts")
    assert row["derived_from"] == "join_ed_visits_visit_id"


def test_released_join_derived_qi_without_join_via_is_rejected() -> None:
    policy, plan = _with_sampled_ts_released(None)
    assert not any("join_via" in r for r in policy.qi if r["column"] == "sampled_ts")
    with pytest.raises(ContractError, match="sampled_ts: join-derived qi needs join_via"):
        generate(policy, plan)


def test_health_contract_carries_k_and_cs_has_none() -> None:
    health = generate(get_policy("HEALTH-S1"), hand_plan("HEALTH-S1"))
    cs = generate(get_policy("CS-S1"), hand_plan("CS-S1"))
    assert health["k"] == 5
    assert "k" not in cs
    without_k = {key: value for key, value in health.items() if key != "k"}
    assert digest(health) != digest(without_k)  # k is part of the canonical digest


def test_policy_k_below_two_is_rejected() -> None:
    policy, plan = get_policy("HEALTH-S1"), hand_plan("HEALTH-S1")
    for bad in (1, 0, -3, True, "5", 2.5):
        targets = tuple({**t, "k": bad} if t["kind"] == "k_anonymity" else t for t in policy.privacy_targets)
        with pytest.raises(ContractError, match="k target"):
            generate(dataclasses.replace(policy, privacy_targets=targets), plan)
    both = (*policy.privacy_targets, next(t for t in policy.privacy_targets if t["kind"] == "k_anonymity"))
    with pytest.raises(ContractError, match="k target"):
        generate(dataclasses.replace(policy, privacy_targets=both), plan)


def test_alt_floor_accepts_fallback_and_param_minimum_is_enforced() -> None:
    policy, plan = get_policy("CS-S1"), hand_plan("CS-S1")
    turn_id = next(e for e in plan if (e["table"], e["column"]) == ("turns", "turn_id"))
    fallback = {**turn_id, "rung": "id.pseudonym", "floor": "id.pseudonym"}
    swapped = [fallback if e is turn_id else e for e in plan]
    # the conditional-keep fallback plan is accepted by the alt floor ...
    assert "turn_id" in generate(policy, swapped)["files"]["turns.csv"]["columns"]
    # ... but an alt floor admits only the alt rung or withheld
    bad = [{**turn_id, "rung": "keep", "floor": "id.pseudonym"} if e is turn_id else e for e in plan]
    with pytest.raises(ContractError, match="turn_id: rung finer than floor"):
        generate(policy, bad)

    health, hplan = get_policy("HEALTH-S1"), hand_plan("HEALTH-S1")
    muni = next(e for e in hplan if (e["table"], e["column"]) == ("ed_visits", "municipality"))
    low = [{**muni, "params": {"n": 3}} if e is muni else e for e in hplan]
    with pytest.raises(ContractError, match="municipality: below policy minimum"):
        generate(health, low)
