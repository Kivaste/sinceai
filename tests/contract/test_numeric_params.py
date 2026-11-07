"""#69, public seams: generate/apply, production contract.forms, and PET narrative.

Rule: numeric releases declare their operative parameters and enforce their grid.
Failure rows (trigger -> result):
  different rounding units -> different contracts/digests and PET parameters
  syntactically valid off-grid decimal -> contract.forms refuses
  bin width/origin (including default origin) -> explicit contract/PET parameters
  syntactically valid shifted/wrong-width interval -> real checks CLI refuses
"""
from __future__ import annotations

import copy
import subprocess
import sys

import pandas as pd
import pytest

from pets_release.checks import all_checks, run_checks
from pets_release.contract import ContractError, digest, generate
from pets_release.ladders import apply
from pets_release.manifest import canonical_bytes
from pets_release.policy.model import FieldFloor, ScenarioPolicy
from pets_release.run.narrative import build_narrative


def numeric_plan(rung, params):
    family, floor = ("geo", "geo.full") if rung == "geo.topn" else ("numeric", "num.exact")
    policy = ScenarioPolicy(
        scenario="HEALTH-S1", dataset="health", purpose_checks=(), privacy_targets=(),
        floors={("t", "value"): FieldFloor(family, floor, "test")},
        direct_identifiers=(), qi=(), risk_vector=(), sacrifices=(), joint_qi_moves=(),
        linked=(), param_minimums={},
    )
    plan = [{"table": "t", "column": "value", "rung": rung, "params": params,
             "floor": floor, "reason": "test", "source": "hand"}]
    return policy, plan


def forms(folder, contract):
    result = run_checks(folder, contract, checks=[c for c in all_checks() if c.name == "contract.forms"])
    return result.records[0]


def test_rounding_units_survive_generation_narrative_and_gate(tmp_path):
    digests = []
    for unit in ("0.5", "2.5"):
        policy, plan = numeric_plan("num.round", {"unit": unit})
        contract = generate(policy, plan)
        assert contract["files"]["t.csv"]["columns"]["value"]["params"] == {
            "nullable": True, "rung": "num.round", "unit": unit,
        }
        narrative = build_narrative(policy=policy, plan=plan, scenario_ids=["HEALTH-S1"], suppression={}, k=None)
        assert narrative["pets"][0]["params"] == {"rung": "num.round", "unit": unit}
        digests.append(digest(contract))
        tables = apply(plan, {"t": pd.DataFrame({"value": ["-1.2", "1.3", ""]})}, None)
        tables["t"].to_csv(tmp_path / "t.csv", index=False)
        assert forms(tmp_path, contract).status == "pass"
        (tmp_path / "t.csv").write_text("value\n1.3\n", encoding="utf-8")
        record = forms(tmp_path, contract)
        assert (record.status, record.hits) == ("fail", 1)
    assert digests[0] != digests[1]


@pytest.mark.parametrize("params, expected", [
    ({"width": "2.5"}, {"width": "2.5", "origin": 0}),
    ({"width": "2.5", "origin": "0.5"}, {"width": "2.5", "origin": "0.5"}),
])
def test_binning_parameters_survive_generation_and_real_cli(tmp_path, params, expected):
    policy, plan = numeric_plan("num.bin", params)
    contract = generate(policy, plan)
    assert contract["files"]["t.csv"]["columns"]["value"]["params"] == {
        "nullable": True, "rung": "num.bin", **expected,
    }
    narrative = build_narrative(policy=policy, plan=plan, scenario_ids=["HEALTH-S1"], suppression={}, k=None)
    assert narrative["pets"][0]["params"] == {"rung": "num.bin", **expected}
    release = tmp_path / "candidate"
    release.mkdir()
    tables = apply(plan, {"t": pd.DataFrame({"value": ["-1.2", "1.3", ""]})}, None)
    tables["t"].to_csv(release / "t.csv", index=False)
    path = tmp_path / "contract.json"
    path.write_bytes(canonical_bytes(contract))

    def check():
        return subprocess.run([sys.executable, "-m", "pets_release.checks", "--contract", str(path),
                               "--check", "contract.forms", str(release)],
                              capture_output=True, text=True, check=False)

    good = check()
    assert good.returncode == 0, good.stdout + good.stderr
    for planted in ("[1.3,3.8)", "[0.5,4.0)", "[3.0,0.5)"):
        pd.DataFrame({"value": [planted]}).to_csv(release / "t.csv", index=False)
        bad = check()
        assert bad.returncode == 1, bad.stdout + bad.stderr
        assert '"status":"fail"' in bad.stdout and '"label":"formMismatch"' in bad.stdout


# Missing/invalid/unknown operative metadata must not become a generic syntax-only check.
@pytest.mark.parametrize("rung, good, bad", [
    ("num.round", {"unit": 1}, {}),
    *[("num.round", {"unit": 1}, {"unit": value})
      for value in (0, -1, True, None, "NaN", "Infinity", {}, [])],
    ("num.round", {"unit": 1}, {"unit": 1, "nullable": False}),
    ("num.bin", {"width": 2, "origin": 0}, {}),
    *[("num.bin", {"width": 2, "origin": 0}, {"width": value, "origin": 0})
      for value in (0, -1, True, None, "NaN", "Infinity", {}, [])],
    *[("num.bin", {"width": 2, "origin": 0}, {"width": 2, "origin": value})
      for value in (True, None, "NaN", "Infinity", {}, [])],
    ("num.bin", {"width": 2, "origin": 0}, {"width": 2, "origin": 0, "unknown": 1}),
    ("num.exact", {}, {"unit": 1}),
    ("geo.topn", {"n": 2}, {}),
    *[("geo.topn", {"n": 2}, {"n": value}) for value in (0, -1, True, "2", 2.5)],
    ("geo.topn", {"n": 2}, {"n": 2, "unknown": 1}),
])
def test_invalid_numeric_metadata_refuses_at_digest_gate_and_generation(tmp_path, rung, good, bad):
    policy, plan = numeric_plan(rung, good)
    contract = generate(policy, plan)
    contract["files"]["t.csv"]["columns"]["value"]["params"] = {"nullable": True, "rung": rung, **bad}
    with pytest.raises(ContractError, match="numeric parameters"):
        digest(contract)
    (tmp_path / "t.csv").write_text("value\n0\n", encoding="utf-8")
    assert forms(tmp_path, contract).status == "error"
    plan[0]["params"] = bad
    with pytest.raises(ContractError, match="numeric parameters"):
        generate(policy, plan)


@pytest.mark.parametrize("mutation", ["missing-origin", "missing-rung", "wrong-form"])
def test_incomplete_or_mismatched_numeric_claims_fail_closed(tmp_path, mutation):
    policy, plan = numeric_plan("num.bin", {"width": 2})
    contract = copy.deepcopy(generate(policy, plan))
    body = contract["files"]["t.csv"]["columns"]["value"]
    if mutation == "missing-origin":
        del body["params"]["origin"]
    elif mutation == "missing-rung":
        del body["params"]["rung"]
    else:
        body["form"] = "text"
    with pytest.raises(ContractError, match="numeric parameters"):
        digest(contract)
    (tmp_path / "t.csv").write_text('value\n"[0,2)"\n', encoding="utf-8")
    assert forms(tmp_path, contract).status == "error"
