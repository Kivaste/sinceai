"""Contracts for ticket 09's real hand plans, through the production generator and CLI."""

from __future__ import annotations

import subprocess
import sys

import pytest

from pets_release.contract import digest, generate
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


def test_released_join_derived_qi_without_join_via_is_rejected() -> None:
    """Real 09 policy, sampled_ts released: the QI must carry join metadata, else reject."""
    import pytest

    from pets_release.contract import ContractError

    policy, plan = get_policy("HEALTH-S1"), hand_plan("HEALTH-S1")
    for entry in plan:
        if (entry["table"], entry["column"]) == ("lab_results", "sampled_ts"):
            entry["rung"], entry["params"] = "ts.month_hour", {}
    row = next(r for r in policy.qi if r["column"] == "sampled_ts")
    if row.get("join_via") is None:
        with pytest.raises(ContractError, match="sampled_ts: join-derived qi needs join_via"):
            generate(policy, plan)
    else:
        contract = generate(policy, plan)
        derived = [r for r in contract["qi"] if r["column"] == "sampled_ts"]
        assert derived[0]["derived_from"].startswith("join_")
