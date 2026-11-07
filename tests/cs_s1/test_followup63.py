"""Must-fix #63: generated CS contracts bind conversational text to its conversation and order.

Rule: the contract generator gives every released redacted free-text column the conversation and
order bindings of its table (CS-S1 ``turns.text``: ``conversation_id``, ``seq``); the bound columns
must be released and required in the same file, else generation is refused. The digest validator
refuses malformed bindings. The gate's text scanner refuses a redacted free-text field without
bindings instead of scanning it row by row.

Failure rows (trigger -> result):
  generated CS-S1 contract                       -> turns.text params name conversation_id / seq
  card split over 2 turns of 1 conversation      -> text.payment-cards fail (was pass, hits 0)
  seq or conversation_id withheld in the plan    -> ContractError (was: unbound text released)
  redacted text in a table without a binding     -> ContractError
  binding to an undeclared / unrequired column   -> digest() ContractError
  redacted text field without bindings at gate   -> text checks error (was: row-by-row pass)
  real contract CLI                              -> CS-S1.contract.json carries the bindings
Synthetic fixture rows only (the public Luhn test card).
"""
from __future__ import annotations

import copy
import csv
import json
import subprocess
import sys

import pytest

from pets_release.checks import run_checks
from pets_release.contract import ContractError, digest, generate
from pets_release.policy import get_policy, hand_plan
from pets_release.policy.model import FieldFloor, ScenarioPolicy

TEST_KEY = "test-only-master-key-0123456789abcdef"  # synthetic test key, as in conftest
REL = {"label": "RECORD_KEY"}
HALVES = ("my card is 4111 1111", "1111 1111")  # the public Luhn test card


def _write(folder, tables):
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        with open(folder / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(list(df.columns))
            w.writerows(df.astype(str).itertuples(index=False, name=None))
    return folder


def _rec(res, name):
    return next(r for r in res.records if r.check == name)


def _split_card(prepared):
    tables = {k: v.copy() for k, v in prepared.tables.items()}
    t = tables["turns"]
    counts = t["conversation_id"].value_counts()
    conv = sorted(c for c, n in counts.items() if n >= 2)[0]
    rows = sorted(t.index[t["conversation_id"] == conv], key=lambda i: int(t.at[i, "seq"]))
    t.at[rows[0], "text"], t.at[rows[1], "text"] = HALVES
    return tables


def test_generated_cs_contract_binds_turn_text():
    contract = generate(get_policy("CS-S1"), hand_plan("CS-S1"))
    spec = contract["files"]["turns.csv"]
    params = spec["columns"]["text"]["params"]
    assert (params.get("conversation"), params.get("order")) == ("conversation_id", "seq")
    assert {"conversation_id", "seq"} <= set(spec["required"])


def test_split_card_across_turns_fails_with_generated_contract(tmp_path, prepared):
    contract = generate(get_policy("CS-S1"), prepared.plan)
    res = run_checks(_write(tmp_path / "rel", _split_card(prepared)), contract,
                     {"phase": "gate", "keys": [TEST_KEY], **prepared.gate_context})
    rec = _rec(res, "text.payment-cards")
    assert (rec.status, rec.hits) == ("fail", 1)
    assert res.refused


@pytest.mark.parametrize("column", ["seq", "conversation_id"])
def test_withheld_binding_column_refuses_generation(column):
    plan = hand_plan("CS-S1")
    for e in plan:
        if (e["table"], e["column"]) == ("turns", column):
            e["rung"], e["params"] = "withheld", {}
    with pytest.raises(ContractError, match="turns.text: conversation binding"):
        generate(get_policy("CS-S1"), plan)


def test_redacted_text_without_a_binding_table_is_refused():
    floors = {("notes", "body"): FieldFloor("text", "text.redacted", "test"),
              ("notes", "person_ref"): FieldFloor("identifier", "id.pseudonym", "test")}
    policy = ScenarioPolicy(
        scenario="X", dataset="d", purpose_checks=(), privacy_targets=(), floors=floors,
        direct_identifiers=(("notes", "person_ref"),), qi=(), risk_vector=(), sacrifices=(),
        joint_qi_moves=(), linked=(), param_minimums={})
    plan = [{"table": "notes", "column": "body", "rung": "text.redacted", "params": {}, "floor": "text.redacted",
             "reason": "t", "source": "hand"},
            {"table": "notes", "column": "person_ref", "rung": "id.pseudonym", "params": REL,
             "floor": "id.pseudonym", "reason": "t", "source": "hand"}]
    with pytest.raises(ContractError, match="notes.body: conversation binding"):
        generate(policy, plan)


@pytest.mark.parametrize("mutate", [
    lambda p, s: p.update(conversation="nope"),              # undeclared column
    lambda p, s: p.pop("order"),                             # only one of the two
    lambda p, s: p.update(order="conversation_id"),          # same column twice
    lambda p, s: p.update(order="text"),                     # the text column itself
    lambda p, s: s["required"].remove("seq"),                # bound column not required
    lambda p, s: p.update(order=7),                          # not a name
])
def test_digest_refuses_malformed_binding(mutate):
    contract = copy.deepcopy(generate(get_policy("CS-S1"), hand_plan("CS-S1")))
    spec = contract["files"]["turns.csv"]
    mutate(spec["columns"]["text"]["params"], spec)
    with pytest.raises(ContractError, match="turns.csv.text: conversation binding"):
        digest(contract)


def test_scanner_refuses_unbound_redacted_text(tmp_path, prepared):
    contract = copy.deepcopy(generate(get_policy("CS-S1"), prepared.plan))
    params = contract["files"]["turns.csv"]["columns"]["text"]["params"]
    params.pop("conversation", None), params.pop("order", None)
    res = run_checks(_write(tmp_path / "rel", _split_card(prepared)), contract,
                     {"phase": "gate", "keys": [TEST_KEY], **prepared.gate_context})
    rec = _rec(res, "text.payment-cards")
    assert rec.status == "error"
    assert res.refused


def test_contract_cli_writes_bound_cs_contract(tmp_path):
    done = subprocess.run([sys.executable, "-m", "pets_release.contract", str(tmp_path)],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    contract = json.loads((tmp_path / "CS-S1.contract.json").read_text(encoding="utf-8"))
    params = contract["files"]["turns.csv"]["columns"]["text"]["params"]
    assert (params["conversation"], params["order"]) == ("conversation_id", "seq")
