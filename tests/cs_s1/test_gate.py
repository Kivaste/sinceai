"""CS-S1 fixture release through the real gate registry (every registered check).

Rule: the prepared CS-S1 release, with the contract generated from the policy and final plan,
passes the gate; the turn-id record is a pass over every turn; the HEALTH-S1-style release without
turns records the turn-id check as not_applicable; a planted card number in a turn refuses.
"""
from __future__ import annotations

import csv

import pytest

from pets_release.checks import run_checks
from pets_release.contract import generate
from pets_release.cs_s1 import TURN_ID_CHECK
from pets_release.policy import get_policy

TEST_KEY = "test-only-master-key-0123456789abcdef"  # same synthetic key as conftest
LUHN_CARD = "4111 1111 1111 1111"  # the standard public test card number


def _write(folder, tables):
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        with open(folder / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(list(df.columns))
            w.writerows(df.astype(str).itertuples(index=False, name=None))
    return folder


def _gate(folder, prepared):
    contract = generate(get_policy("CS-S1"), prepared.plan)
    # key material comes from the run (ticket 21); here the synthetic test key
    return run_checks(folder, contract, {"phase": "gate", "keys": [TEST_KEY], **prepared.gate_context})


def _rec(res, name):
    return next(r for r in res.records if r.check == name)


@pytest.mark.xfail(strict=True, reason="ticket 04 defect: rescan.secrets treats an ordinary word after a "
                   "secret cue ('wifi password for the router') as a secret; 05's text.secrets does not")
def test_fixture_release_passes_gate(tmp_path, prepared):
    res = _gate(_write(tmp_path / "rel", prepared.tables), prepared)
    bad = sorted((r.check, r.status) for r in res.records if r.status not in ("pass", "not_applicable"))
    assert bad == [] and not res.refused


@pytest.mark.parametrize("which", ["prepared", "kept"])  # turn_id pseudonymised / kept as-is
def test_only_known_defect_refuses_fixture_release(tmp_path, request, which):
    prepared = request.getfixturevalue(which)
    res = _gate(_write(tmp_path / "rel", prepared.tables), prepared)
    bad = sorted((r.check, r.status) for r in res.records if r.status not in ("pass", "not_applicable"))
    assert bad in ([], [("rescan.secrets", "fail")])
    rec = _rec(res, TURN_ID_CHECK)
    assert (rec.status, rec.hits, rec.denominator["n"]) == ("pass", 0, len(prepared.tables["turns"]))


def test_contract_has_no_k(prepared):
    assert "k" not in generate(get_policy("CS-S1"), prepared.plan)


def test_planted_card_in_turn_refuses(tmp_path, prepared):
    tables = {k: v.copy() for k, v in prepared.tables.items()}
    t = tables["turns"]
    t.iloc[3, t.columns.get_loc("text")] = f"my card number is {LUHN_CARD} thanks"
    res = _gate(_write(tmp_path / "rel", tables), prepared)
    assert res.refused
    assert any(r.status == "fail" for r in res.records if "payment-cards" in r.check)


def test_turn_id_check_not_applicable_without_turns(tmp_path, prepared):
    tables = {"conversations": prepared.tables["conversations"]}
    folder = _write(tmp_path / "rel", tables)
    contract = generate(get_policy("CS-S1"), prepared.plan)
    contract["files"].pop("turns.csv")
    contract["tokens"] = [x for x in contract["tokens"] if x["table"] != "turns"]
    res = run_checks(folder, contract, {"phase": "gate", **prepared.gate_context})
    assert _rec(res, TURN_ID_CHECK).status == "not_applicable"
