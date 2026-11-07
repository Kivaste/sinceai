"""CS-S1 glue on ticket 03's synthetic minikit: ``pets_release.cs_s1.prepare``.

Rule: the CS-S1 release keeps only the policy's released columns; conversation_id is one
release-scope pseudonym across conversations and turns; split is kept; timestamps are at the hour;
turns.text is redacted with per-conversation placeholders using a controller gazetteer built at
runtime; turns.turn_id is kept iff producer.turn-id-synthetic passes on the candidate, else the
release-scope pseudonym fallback with lineage restoration for scoring.
"""
from __future__ import annotations

import re

import pandas as pd
import pytest

from pets_release.cs_s1 import TURN_ID_CHECK, prepare, restore_turn_ids
from pets_release.policy import get_policy, validate_plan

HEX64 = re.compile(r"^[0-9a-f]{64}$")
HOUR = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:00$")


def test_only_conversations_and_turns_released(prepared):
    assert sorted(prepared.tables) == ["conversations", "turns"]
    conv_cols = set(prepared.tables["conversations"].columns)
    assert not conv_cols & {"customer_id", "agent_name", "agent_note"}
    assert {"split", "intent", "handle_time_s", "conversation_id"} <= conv_cols


def test_conversation_id_is_one_pseudonym_across_tables(prepared, minikit):
    c = prepared.tables["conversations"].conversation_id
    t = prepared.tables["turns"].conversation_id
    assert c.map(lambda v: bool(HEX64.match(v))).all()
    assert set(t) == set(c)
    assert not set(c) & set(minikit["conversations"].conversation_id)
    # same partition as the source: each source conversation maps to exactly one token
    src = minikit["turns"].conversation_id
    pairs = pd.DataFrame({"s": src.to_numpy(), "p": t.to_numpy()})
    assert pairs.groupby("s").p.nunique().max() == 1 and pairs.p.nunique() == src.nunique()


def test_split_kept(prepared, minikit):
    assert prepared.tables["conversations"].split.tolist() == minikit["conversations"].split.tolist()


def test_timestamps_at_hour(prepared):
    for t, c in (("conversations", "started_ts"), ("turns", "ts")):
        s = prepared.tables[t][c]
        assert s.map(lambda v: bool(HOUR.match(v))).all(), (t, c)


def test_plan_is_valid_hand_plan_with_turn_id_kept(kept):
    validate_plan(kept.plan, get_policy("CS-S1"))
    entry = next(e for e in kept.plan if (e["table"], e["column"]) == ("turns", "turn_id"))
    assert entry["rung"] == "keep"
    assert kept.turn_id.kept is True
    assert kept.turn_id.assessment == {"check": TURN_ID_CHECK, "status": "pass", "n": len(kept.tables["turns"]),
                                       "hits": {}}
    ids = {(d["table"], d["column"]) for d in kept.gate_context["identifiers"]}
    assert ("turns", "turn_id") not in ids


def test_generated_minikit_turn_ids_leak_conversation_order(prepared):
    # ticket 03's counter follows conversation order, as the real kit's does: fallback
    assert prepared.turn_id.kept is False
    assert prepared.turn_id.assessment["hits"] == {"conversationOrder": len(prepared.tables["turns"])}
    assert prepared.tables["turns"].turn_id.map(lambda v: bool(HEX64.match(v))).all()


@pytest.mark.parametrize("which", ["kept", "prepared"])
def test_turn_id_justification_names_the_check(request, which):
    p = request.getfixturevalue(which)
    j = p.turn_id.justification
    assert j["table"] == "turns" and j["column"] == "turn_id" and TURN_ID_CHECK in j["reason"]
    assert j["rung"] == ("keep" if p.turn_id.kept else "id.pseudonym")
    assert set(j) == {"table", "column", "outputColumn", "decision", "rung", "floor", "reason", "source"}
    assert 0 < len(j["reason"]) <= 500


def test_text_redacted_with_per_conversation_placeholders(prepared, minikit):
    # every customer full name in the fixture is spoken in its conversation; none may survive
    names = set(minikit["customers"].full_name)
    texts = prepared.tables["turns"].text
    assert not any(n in t for t in texts for n in names)
    assert prepared.spans, "redactor produced no spans"
    ph = re.compile(r"\[[A-Z_]+_(\d+)\]")
    per_conv: dict = {}
    for cid, txt in zip(prepared.tables["turns"].conversation_id, texts):
        per_conv.setdefault(cid, set()).update(int(n) for n in ph.findall(txt))
    # numbering restarts in every conversation: the first placeholder number is 1 everywhere
    assert all(min(v) == 1 for v in per_conv.values() if v)
    assert {s["record_id"] for s in prepared.spans} <= set(minikit["turns"].turn_id)


@pytest.mark.parametrize("column,label", [("customer_number", "ACCOUNT_NUMBER"), ("email", "EMAIL")])
def test_controller_identifier_values_redacted(prepared, minikit, column, label):
    values = {v for v in minikit["customers"][column] if v}
    spoken = [t for t in minikit["turns"].text if any(v in t for v in values)]
    assert spoken, "fixture must mention the values"
    assert not any(v in t for t in prepared.tables["turns"].text for v in values)
    assert any(s["label"] == label for s in prepared.spans)


def test_controller_values_pass_matches_whole_tokens_only():
    from pets_release.cs_s1.prepare import ControllerValuesPass
    from pets_release.redactor import ConversationView, Turn

    p = ControllerValuesPass({"ACCOUNT_NUMBER": {"AB123456"}})
    view = ConversationView("c", (Turn("t1", "nr AB123456, not XAB1234567 or ab123456x"),))
    got = [(c.start, c.end, c.label) for c in p.run(view)]
    assert got == [(3, 11, "ACCOUNT_NUMBER")]


def test_controller_values_pass_matches_multi_token_values_anywhere():
    from pets_release.cs_s1.prepare import ControllerValuesPass
    from pets_release.redactor import ConversationView, Turn

    p = ControllerValuesPass({"PERSON": {"Aino Mäki-Ojala"}, "ADDRESS": {"Rantatie 12 B"}})
    text = "hi aino  mäki-ojala, I moved from Rantatie 12 B 4 to Rantatie 12, Ainomäki-Ojala"
    got = [(text[c.start:c.end], c.label) for c in p.run(ConversationView("other", (Turn("t", text),)))]
    assert got == [("aino  mäki-ojala", "PERSON"), ("Rantatie 12 B", "ADDRESS")]


def test_ip_literals_cover_private_and_spaced_but_not_times_or_bad_octets():
    from pets_release.cs_s1.prepare import ip_literals

    text = "a 10.0.0.1 b 192 . 168 . 1 . 2 c 12:30:45 d 300.1.1.1 e fe80::1 f 1.2.3.4.5"
    got = [text[s:e] for s, e in ip_literals(text)]
    assert got == ["10.0.0.1", "192 . 168 . 1 . 2", "fe80::1"]


def test_controller_values_cover_names_and_addresses(prepared, minikit):
    for col in ("full_name", "street_address"):
        values = {v for v in minikit["customers"][col] if v}
        assert not any(v in t for t in prepared.tables["turns"].text for v in values), col


def test_gazetteer_is_built_from_controller_tables(prepared):
    assert prepared.gazetteer  # non-empty, in memory only
    assert prepared.gazetteer.parties


def test_gate_context_lists_source_identifiers(prepared):
    ids = {(d["table"], d["column"]) for d in prepared.gate_context["identifiers"]}
    assert ("turns", "turn_id") in ids  # pseudonymised: originals must not survive
    assert {("customers", "full_name"), ("conversations", "agent_name"), ("conversations", "conversation_id")} <= ids
    assert set(prepared.gate_context["source"]) == {"conversations", "customers", "turns"}


def test_deterministic(minikit, prepared, make_keys):
    again = prepare(minikit, make_keys())
    for t in prepared.tables:
        pd.testing.assert_frame_equal(prepared.tables[t], again.tables[t])
    assert prepared.spans == again.spans


def _conv_encoded(minikit):
    src = {k: v.copy() for k, v in minikit.items()}
    t = src["turns"]
    t["turn_id"] = [f"{c}-{s}" for c, s in zip(t.conversation_id, t.seq)]
    return src


@pytest.fixture(scope="module")
def fallback(minikit, make_keys):
    return prepare(_conv_encoded(minikit), make_keys())


def test_fallback_pseudonymises_turn_id(fallback):
    assert fallback.turn_id.kept is False
    assert fallback.turn_id.assessment["status"] == "fail"
    assert "conversationComponent" in fallback.turn_id.assessment["hits"]
    entry = next(e for e in fallback.plan if (e["table"], e["column"]) == ("turns", "turn_id"))
    assert (entry["rung"], entry["floor"]) == ("id.pseudonym", "id.pseudonym")
    validate_plan(fallback.plan, get_policy("CS-S1"))
    assert fallback.tables["turns"].turn_id.map(lambda v: bool(HEX64.match(v))).all()
    ids = {(d["table"], d["column"]) for d in fallback.gate_context["identifiers"]}
    assert ("turns", "turn_id") in ids


def test_lineage_restores_source_turn_ids(fallback, minikit):
    src = _conv_encoded(minikit)["turns"]
    prot = fallback.tables["turns"].iloc[::-1].reset_index(drop=True)  # a writer may reorder rows
    order = list(range(len(src)))[::-1]
    rowmap = pd.DataFrame({"protected_row": [str(i) for i in range(len(prot))],
                           "original_record_id": [src.turn_id.iloc[j] for j in order]})
    restored = restore_turn_ids(prot, rowmap)
    assert restored.turn_id.tolist() == [src.turn_id.iloc[j] for j in order]
    assert restored.text.tolist() == prot.text.tolist()


@pytest.mark.parametrize("bad", ["missing_row", "duplicate", "extra"])
def test_lineage_rejects_incomplete_rowmap(fallback, bad):
    from pets_release.cs_s1 import LineageError

    prot = fallback.tables["turns"].reset_index(drop=True)
    rm = pd.DataFrame({"protected_row": [str(i) for i in range(len(prot))],
                       "original_record_id": [f"o{i}" for i in range(len(prot))]})
    if bad == "missing_row":
        rm = rm.iloc[1:]
    elif bad == "duplicate":
        rm.loc[1, "original_record_id"] = "o0"
    else:
        rm = pd.concat([rm, pd.DataFrame({"protected_row": [str(len(prot))], "original_record_id": ["ox"]})])
    with pytest.raises(LineageError):
        restore_turn_ids(prot, rm)
