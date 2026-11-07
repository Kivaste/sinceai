"""CS health policy through generated contracts, production checks and the real CLI.

Rule: CS-S1's zero-health privacy target must survive contract generation and validation.
Rows (trigger -> result):
  generated CS contract + synthetic health term -> text.health fails, high severity
  missing/false/non-boolean requirement -> contract digest and contract.forms error
  CS manifest missing/false/non-boolean requirement -> schema rejects
  generated CS contract + no health terms -> CLI check passes with positive denominator
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from pets_release.checks import registry
from pets_release.checks.runner import run_checks
from pets_release.contract import ContractError, digest, generate
from pets_release.policy import get_policy, hand_plan


def _cs_candidate(tmp_path, *, health=True):
    contract = generate(get_policy("CS-S1"), hand_plan("CS-S1"))
    source = Path(__file__).resolve().parents[1] / "fixtures" / "minikit" / "customer_service" / "turns.csv"
    turns = pd.read_csv(source, dtype=str, keep_default_na=False).head(2).copy()
    turns["text"] = "Please correct the invoice"
    if health:
        turns.loc[0, "text"] = "I have diabetes"
    release = tmp_path / "candidate"
    release.mkdir()
    for name, spec in contract["files"].items():
        frame = turns if name == "turns.csv" else pd.read_csv(source.with_name(name), dtype=str, keep_default_na=False)
        frame[list(spec["columns"])].to_csv(release / name, index=False)
    return release, contract


def test_generated_cs_contract_makes_health_hits_high_severity(tmp_path):
    release, contract = _cs_candidate(tmp_path)
    checks = [c for c in registry.all_checks() if c.name == "text.health"]
    result = run_checks(release, contract, {"phase": "gate"}, checks=checks)
    (record,) = result.records
    assert result.refused
    assert record.status == "fail" and record.hits == 1
    assert record.violations[0].severity == "high"
    assert contract["healthInTextRequired"] is True
    assert digest(contract) == digest(generate(get_policy("CS-S1"), list(reversed(hand_plan("CS-S1")))))


@pytest.mark.parametrize("value", ["missing", False, None, 1, "0", "duplicate"])
def test_cs_generation_requires_one_zero_health_policy_target(value):
    policy = get_policy("CS-S1")
    target = next(t for t in policy.privacy_targets if t["kind"] == "health_in_text")
    others = tuple(t for t in policy.privacy_targets if t["kind"] != "health_in_text")
    if value == "missing":
        targets = others
    elif value == "duplicate":
        targets = (*others, target, target)
    else:
        targets = (*others, {**target, "max_hits": value})
    with pytest.raises(ContractError, match="health"):
        generate(replace(policy, privacy_targets=targets), hand_plan("CS-S1"))


@pytest.mark.parametrize("value", ["missing", False, None, 0, 1, "true"])
def test_cs_requirement_cannot_be_omitted_or_weakened(tmp_path, value):
    release, contract = _cs_candidate(tmp_path, health=False)
    if value == "missing":
        contract.pop("healthInTextRequired", None)
    else:
        contract["healthInTextRequired"] = value
    with pytest.raises(ContractError, match="healthInTextRequired"):
        digest(contract)
    checks = [c for c in registry.all_checks() if c.name == "contract.forms"]
    result = run_checks(release, contract, {"phase": "gate"}, checks=checks)
    assert result.refused
    assert result.records[0].status == "error"


def test_planted_contract_cannot_supply_missing_health_requirement(tmp_path):
    release, contract = _cs_candidate(tmp_path, health=False)
    (release / "CS-S1.contract.json").write_text(
        json.dumps({**contract, "healthInTextRequired": True}), encoding="utf-8",
    )
    contract.pop("healthInTextRequired", None)
    checks = [c for c in registry.all_checks() if c.name == "contract.forms"]
    result = run_checks(release, contract, {"phase": "gate"}, checks=checks)
    assert result.refused and result.records[0].status == "error"


@pytest.mark.parametrize("health", [True, False])
def test_real_cli_checks_generated_cs_health_policy(tmp_path, health):
    release, contract = _cs_candidate(tmp_path, health=health)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pets_release.checks", "--phase", "gate", "--check", "text.health",
         "--contract", str(path), str(release)],
        capture_output=True, text=True, check=False, env=os.environ.copy(),
    )
    assert proc.returncode == (1 if health else 0), proc.stderr
    summary = json.loads(proc.stdout)
    (record,) = summary["records"]
    assert record["status"] == ("fail" if health else "pass")
    assert record["hits"] == (1 if health else 0)
    assert record["denominator"]["n"] > 0
