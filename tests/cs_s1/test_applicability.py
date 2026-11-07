"""Applicability selectors (ticket 23 change to 04's runner).

Rule: a check registered with ``applies_to`` may return ``not_applicable`` only when the contract
declares none of its selectors. Selectors: a column form (04's original rule), ``contract:k`` (the
contract carries a k target), ``column:<file>/<column>`` (the contract releases that column).
Anything else, or a not_applicable claim the contract contradicts, is an error (refuses).
"""
from __future__ import annotations

import pytest

from pets_release.checks import Check, Outcome, RegistryError, register, run_checks


def _na(release, contract, context):
    return Outcome.not_applicable()


def _chk(*applies_to):
    return Check(name="demo.na", version="1.0.0", scope="release", unit="rows", run=_na, applies_to=applies_to)


def _contract(k=None, turn_id=True):
    cols = {"conversation_id": {"form": "hex64", "params": {}}}
    if turn_id:
        cols["turn_id"] = {"form": "text", "params": {}}
    c = {"files": {"turns.csv": {"columns": cols, "required": sorted(cols)}}, "qi": [], "tokens": []}
    if k is not None:
        c["k"] = k
    return c


@pytest.fixture
def release(tmp_path):
    (tmp_path / "turns.csv").write_text("conversation_id\nx\n", encoding="utf-8")
    return tmp_path


def _status(release, check, contract):
    return run_checks(release, contract, {}, checks=[check]).records[0].status


def test_k_selector_not_applicable_without_contract_k(release):
    assert _status(release, _chk("contract:k"), _contract()) == "not_applicable"


def test_k_selector_claim_is_error_when_contract_has_k(release):
    assert _status(release, _chk("contract:k"), _contract(k=5)) == "error"


def test_column_selector_not_applicable_when_column_absent(release):
    assert _status(release, _chk("column:turns.csv/turn_id"), _contract(turn_id=False)) == "not_applicable"


def test_column_selector_claim_is_error_when_column_released(release):
    assert _status(release, _chk("column:turns.csv/turn_id"), _contract()) == "error"


def test_unreadable_contract_counts_as_applicable(release):
    assert _status(release, _chk("contract:k"), {"files": None}) == "error"


@pytest.mark.parametrize("bad", ["contract:", "contract:qi", "column:turns.csv", "column:/x", "other:k"])
def test_unknown_selector_is_rejected_at_registration(bad):
    with pytest.raises(RegistryError):
        register(name="demo.bad", version="1.0.0", scope="release", unit="rows", applies_to=(bad,))
