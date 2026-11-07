"""``turn-id-synthetic`` through the real registry and runner (D21).

Rule: a released ``turns.turn_id`` passes only if it is a record key (non-empty, unique) carrying
no conversation information (no component constant within each conversation and varying across
them; no original conversation_id inside it), no original identifier value and no source
timestamp finer than the released hour. Rows:

  column not released                  -> not_applicable
  source / identifiers missing         -> not_run (refuses)
  counter shuffled across conversations-> pass, n = turn rows
  counter in (reverse) conversation order -> fail conversationOrder
  few-valued prefix (< half the conversations) -> pass
  values not in source, undeclared     -> fail undetermined
  declared tokens over original source -> pass
  duplicate or empty key               -> fail duplicateKey / emptyKey
  conversation component (prefix/token)-> fail conversationComponent
  original conversation_id inside      -> fail conversationComponent
  original identifier value inside     -> fail identifierValue
  minute-level source timestamp inside -> fail sourceTimestamp
  released turns without conversation_id -> error
  < 2 multi-turn conversations         -> fail undetermined
  hex64 release-scope tokens (fallback)-> pass
"""
from __future__ import annotations

import csv
import hashlib
import random

import pandas as pd
import pytest

from pets_release.checks import all_checks, run_checks

NAME = "turn-id-synthetic"


def _check():
    (c,) = [c for c in all_checks() if c.name == NAME]
    return c


def _contract(turn_id=True):
    cols = {"conversation_id": {"form": "hex64", "params": {}}, "text": {"form": "text", "params": {}}}
    if turn_id:
        cols["turn_id"] = {"form": "text", "params": {}}
    return {"files": {"turns.csv": {"columns": cols, "required": sorted(cols)}}, "qi": [],
            "tokens": [{"table": "turns", "column": "conversation_id", "scope": "release"}]}


def _tok(v):
    return hashlib.sha256(v.encode()).hexdigest()


CONVS = [f"QX-{i:04d}" for i in range(1, 31)]
SIZES = [3, 4, 2, 5, 3, 4] * 5
_PERM = list(range(1, sum(SIZES) + 1))
random.Random(11).shuffle(_PERM)  # turn numbers shuffled across conversations: no order information


def _source(turn_ids=None):
    rows, n = [], 0
    for cid, size in zip(CONVS, SIZES):
        for s in range(1, size + 1):
            n += 1
            rows.append({"turn_id": f"TT-{_PERM[n - 1]:06d}", "conversation_id": cid, "seq": str(s),
                         "ts": f"2025-03-0{s} 1{s}:2{s}:0{s}", "text": "hello"})
    turns = pd.DataFrame(rows, dtype=str)
    if turn_ids is not None:
        turns["turn_id"] = turn_ids(turns)
    convs = pd.DataFrame({"conversation_id": CONVS, "customer_id": [f"CUSTOMER{i:05d}" for i in range(len(CONVS))],
                          "started_ts": ["2025-03-01 10:11:12"] * len(CONVS)}, dtype=str)
    return {"turns": turns, "conversations": convs}


def _context(source):
    return {"source": source, "identifiers": [{"table": "conversations", "column": "customer_id"},
                                              {"table": "conversations", "column": "conversation_id"}]}


def _release(tmp_path, source, with_conv=True):
    t = source["turns"]
    with open(tmp_path / "turns.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["conversation_id", "text", "turn_id"] if with_conv else ["text", "turn_id"])
        for _, r in t.iterrows():
            row = [_tok(r.conversation_id), r.text, r.turn_id] if with_conv else [r.text, r.turn_id]
            w.writerow(row)
    return tmp_path


def _run(tmp_path, source, contract=None, context=None, with_conv=True):
    rel = _release(tmp_path, source, with_conv)
    res = run_checks(rel, contract or _contract(), _context(source) if context is None else context,
                     checks=[_check()])
    return res.records[0]


def _labels(rec):
    return {v.label for v in rec.violations}


def test_registered_as_producer_turns_check():
    c = _check()
    assert (c.scope, c.unit) == ("producer", "turns")


def test_not_applicable_when_turn_id_not_released(tmp_path):
    assert _run(tmp_path, _source(), contract=_contract(turn_id=False)).status == "not_applicable"


@pytest.mark.parametrize("drop", ["source", "identifiers"])
def test_not_run_without_producer_inputs(tmp_path, drop):
    ctx = _context(_source())
    del ctx[drop]
    assert _run(tmp_path, _source(), context=ctx).status == "not_run"


def test_shuffled_counter_ids_pass(tmp_path):
    rec = _run(tmp_path, _source())
    assert (rec.status, rec.hits, rec.denominator) == ("pass", 0, {"unit": "turns", "n": sum(SIZES)})


def test_counter_in_conversation_order_fails(tmp_path):
    # contiguous global counter: ranking conversations by turn_id rebuilds the conversation_id order
    src = _source(lambda t: [f"TT-{i:06d}" for i in range(1, len(t) + 1)])
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and _labels(rec) == {"conversationOrder"}


def test_counter_in_reverse_conversation_order_fails(tmp_path):
    src = _source(lambda t: [f"TT-{i:06d}" for i in range(len(t), 0, -1)])
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and "conversationOrder" in _labels(rec)


def test_few_valued_prefix_is_not_a_conversation_component(tmp_path):
    # a high-order prefix constant within conversations but with 2 values over 30 conversations
    # (e.g. a counter's leading digit) carries about one bit, not the conversation
    src = _source()
    t = src["turns"]
    first = set(CONVS[::2])  # interleaved, so the split carries no conversation order either
    t["turn_id"] = [("A" if c in first else "B") + v for c, v in zip(t.conversation_id, t.turn_id)]
    assert _run(tmp_path, src).status == "pass"


def test_duplicate_key_fails(tmp_path):
    src = _source(lambda t: ["TT-000001"] * 2 + [f"TT-{i:06d}" for i in range(3, len(t) + 1)])
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and "duplicateKey" in _labels(rec)


def test_empty_key_fails(tmp_path):
    src = _source(lambda t: [""] + list(t.turn_id[1:]))
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and "emptyKey" in _labels(rec)


def test_conversation_prefix_fails(tmp_path):
    # conversation number encoded as a prefix, sequence as suffix
    src = _source(lambda t: [f"Z{CONVS.index(c) * 7 + 11:03d}{s:0>2}" for c, s in zip(t.conversation_id, t.seq)])
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and "conversationComponent" in _labels(rec)


def test_conversation_token_fails(tmp_path):
    src = _source(lambda t: [f"{s}-K{CONVS.index(c) * 13 + 5}" for c, s in zip(t.conversation_id, t.seq)])
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and "conversationComponent" in _labels(rec)


def test_original_conversation_id_inside_fails(tmp_path):
    # unique per turn, no constant component, but one row embeds its original conversation_id
    src = _source(lambda t: [f"TT-{i:06d}" for i in range(1, len(t))] + [f"x{t.conversation_id.iloc[-1]}"])
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and "conversationComponent" in _labels(rec)


def test_identifier_value_inside_fails(tmp_path):
    src = _source(lambda t: list(t.turn_id[:-1]) + ["ab-customer00003-z"])
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and _labels(rec) == {"identifierValue"}


def test_minute_timestamp_inside_fails(tmp_path):
    src = _source(lambda t: list(t.turn_id[:-1]) + ["t202503011011-9"])
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and _labels(rec) == {"sourceTimestamp"}


def test_missing_conversation_column_is_error(tmp_path):
    contract = _contract()
    del contract["files"]["turns.csv"]["columns"]["conversation_id"]
    contract["files"]["turns.csv"]["required"] = ["text", "turn_id"]
    contract["tokens"] = []
    assert _run(tmp_path, _source(), contract=contract, with_conv=False).status == "error"


def test_single_multi_turn_conversation_is_undetermined(tmp_path):
    src = _source()
    src["turns"] = src["turns"][src["turns"].conversation_id.isin(["QX-0001", "QX-0002"]) &
                                ~((src["turns"].conversation_id == "QX-0002") & (src["turns"].seq != "1"))]
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and "undetermined" in _labels(rec)


def test_release_scope_tokens_pass(tmp_path):
    src = _source(lambda t: [_tok("salt" + v) for v in t.turn_id])
    assert _run(tmp_path, src, contract=_token_contract()).status == "pass"


def test_fallback_tokens_over_original_source_pass(tmp_path):
    # the real fallback: source keeps the (order-leaking) originals, the release carries keyed tokens
    src = _source(lambda t: [f"TT-{i:06d}" for i in range(1, len(t) + 1)])
    rel_src = {k: v.copy() for k, v in src.items()}
    rel_src["turns"]["turn_id"] = [_tok("salt" + v) for v in src["turns"].turn_id]
    rel = _release(tmp_path, rel_src)
    rec = run_checks(rel, _token_contract(), _context(src), checks=[_check()]).records[0]
    assert (rec.status, rec.hits) == ("pass", 0)


def test_undeclared_values_not_in_source_are_undetermined(tmp_path):
    # order can only be tested for kept source IDs or declared keyed tokens
    src = {k: v.copy() for k, v in _source().items()}
    rel_src = _source(lambda t: [f"ZZ-{v}" for v in t.turn_id])
    rel = _release(tmp_path, rel_src)
    rec = run_checks(rel, _contract(), _context(src), checks=[_check()]).records[0]
    assert rec.status == "fail" and "undetermined" in _labels(rec)


def _token_contract():
    c = _contract()
    c["files"]["turns.csv"]["columns"]["turn_id"] = {"form": "hex64", "params": {}}
    c["tokens"] = sorted(c["tokens"] + [{"table": "turns", "column": "turn_id", "scope": "release"}],
                         key=lambda r: (r["table"], r["column"]))
    return c


def test_declared_token_containing_identifier_by_chance_passes(tmp_path):
    # a keyed 64-hex token can contain an 8+ char identifier by coincidence; not information
    src = _source(lambda t: [_tok("salt" + v) for v in t.turn_id])
    src["conversations"].loc[0, "customer_id"] = src["turns"].turn_id.iloc[2][10:20]
    assert _run(tmp_path, src, contract=_token_contract()).status == "pass"


def test_undeclared_hex_containing_identifier_fails(tmp_path):
    src = _source(lambda t: [_tok("salt" + v) for v in t.turn_id])
    src["conversations"].loc[0, "customer_id"] = src["turns"].turn_id.iloc[2][10:20]
    rec = _run(tmp_path, src)
    assert rec.status == "fail" and "identifierValue" in _labels(rec)


def test_declared_token_still_needs_unique_keys(tmp_path):
    src = _source(lambda t: [_tok("same")] * 2 + [_tok("salt" + v) for v in t.turn_id[2:]])
    rec = _run(tmp_path, src, contract=_token_contract())
    assert rec.status == "fail" and "duplicateKey" in _labels(rec)
