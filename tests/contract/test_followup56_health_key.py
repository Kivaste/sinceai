"""Must-fix #56 (contract side): every generated contract states ``healthInTextRequired`` explicitly.

Rows (trigger -> result):
  policy with a health_in_text target (CS-S1)   -> contract healthInTextRequired is True
  policy without one (HEALTH-S1)                -> contract healthInTextRequired is False
  contract with a non-bool value                -> ContractError at validation
(The text check treats a missing key as required: tests/checks_text/test_followup56.py.)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pets_release.contract import generate
from pets_release.contract.generate import ContractError, _validate_contract
from pets_release.policy import get_policy, hand_plan


def test_health_s1_contract_states_health_not_required():
    c = generate(get_policy("HEALTH-S1"), hand_plan("HEALTH-S1"))
    assert c["healthInTextRequired"] is False


def test_cs_s1_contract_states_health_required():
    import pandas as pd

    from pets_release.cs_s1 import prepare
    from pets_release.ladders import PseudonymKeys
    from pets_release.pseudonym import MasterKey, Scope, pseudonymiser_for

    mini = Path(__file__).resolve().parents[1] / "fixtures" / "minikit" / "customer_service"
    src = {p.stem: pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False) for p in sorted(mini.glob("*.csv"))}
    keys = PseudonymKeys(pseudonymiser_for(MasterKey.from_text("test-only-master-key-0123456789abcdef")),
                         Scope.release("0123456789abcdef"))
    prep = prepare(src, keys)
    c = generate(get_policy("CS-S1"), prep.plan)
    assert c["healthInTextRequired"] is True


@pytest.mark.parametrize("bad", ["yes", 1, None])
def test_non_bool_requirement_is_rejected(bad):
    c = generate(get_policy("HEALTH-S1"), hand_plan("HEALTH-S1"))
    c["healthInTextRequired"] = bad
    with pytest.raises(ContractError):
        _validate_contract(c)
