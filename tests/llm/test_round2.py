"""Review round 2: no free-text metadata on the wire, call-site type enforcement, short keys, AC3 exit codes."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fake_provider import FakeProvider
from llm_helpers import DICT_MD

from pets_release.llm.client import LlmConfig, LlmError, draft_policy, resolve_config
from pets_release.llm.dictionary import ColumnInfo, DataDictionary, DictionaryError, TableInfo, parse_dictionary
from pets_release.llm.prompt import build_messages
from pets_release.llm.vocabulary import vocabulary_for

GOOD = {
    "recipient": "University research group",
    "trustLevel": "controlled_research",
    "purposeChecks": [{"id": "H-U2", "reason": "length of stay"}],
    "fieldsNeeded": [{"table": "ed_visits", "column": "when", "detail": "exact", "reason": "time"}],
}
# Planted values a description could carry that a regex screen misses.
PLANTS = {
    "name": "Mikael Virtanen",
    "ipv4": "192.168.10.77",
    "mac": "aa:bb:cc:dd:ee:ff",
    "record_id": "ED25-777001",
    "birth_date": "1970-01-01",
    "free": "Mikael works in Oulu",
}


def _md(desc):
    return (
        "# Data dictionary\n\n## health\n\n### health / ed_visits\n\n"
        "| column | role | subtype | Art. 9 | description |\n|---|---|---|---|---|\n"
        f"| `when` | quasi_identifier | DATE |  | {desc} |\n"
    )


def _chat(obj):
    return json.dumps({"choices": [{"message": {"content": json.dumps(obj)}}]}).encode()


@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_transport_bytes_contain_no_description_text(plant):
    sent = []

    def transport(url, body, key, timeout):
        sent.append(body)
        return _chat(GOOD)

    d = parse_dictionary(_md(f"Seen: {PLANTS[plant]} ok"), "health")
    draft_policy("req", d, LlmConfig("http://localhost:1/v1", "m", ""), transport)
    (body,) = sent
    assert PLANTS[plant].encode() not in body
    assert b"Seen:" not in body
    assert b"when" in body and b"quasi_identifier" in body  # names, roles, subtypes still go out


def test_cli_ipv4_and_mac_in_description_absent_from_the_wire(cli, make_kit, tmp_path):
    p = FakeProvider(tmp_path / "provider", reply=GOOD)
    try:
        kit = make_kit(dictionary=_md(f"host {PLANTS['ipv4']} {PLANTS['mac']} {PLANTS['name']}"))
        r = cli("draft-policy", "--request", "Researchers want visit times", "--dataset", "health",
                "--allow-network", "--kit", str(kit), env=p["env"])
        bodies = p["bodies"]
    finally:
        p.close()
    assert r.returncode == 0, r.stderr
    wire = bodies[0].decode()
    for v in PLANTS.values():
        assert v not in wire


def test_column_info_has_no_free_text_field():
    assert not hasattr(ColumnInfo("c", "record_key", "RECORD_ID"), "description")
    with pytest.raises(TypeError):
        ColumnInfo("c", "record_key", "RECORD_ID", "free text")  # type: ignore[call-arg]


# ---- call-site type enforcement -----------------------------------------------------------------


def test_stand_in_children_are_rejected_at_construction():
    fake_col = SimpleNamespace(name="c", role="record_key", subtype="RECORD_ID")
    with pytest.raises(DictionaryError):
        TableInfo("t", (fake_col,))  # type: ignore[arg-type]
    fake_table = SimpleNamespace(name="t", columns=())
    with pytest.raises(DictionaryError):
        DataDictionary("health", (fake_table,))  # type: ignore[arg-type]
    with pytest.raises(DictionaryError):
        TableInfo("t", [ColumnInfo("c", "record_key", "RECORD_ID")])  # type: ignore[arg-type]


def test_build_messages_revalidates_even_if_construction_was_bypassed():
    d = parse_dictionary(DICT_MD, "health")
    col = d.tables[0].columns[0]
    object.__setattr__(col, "name", "leak@example.org")
    with pytest.raises(DictionaryError):
        build_messages("req", d, vocabulary_for("health"))
    d2 = parse_dictionary(DICT_MD, "health")
    object.__setattr__(d2.tables[0], "columns", (SimpleNamespace(name="c", role="record_key", subtype="RECORD_ID"),))
    with pytest.raises((DictionaryError, TypeError)):
        build_messages("req", d2, vocabulary_for("health"))


def test_stand_in_dictionary_never_reaches_the_transport():
    calls = []
    stand_in = SimpleNamespace(dataset="health", tables=())
    with pytest.raises((TypeError, DictionaryError)):
        draft_policy("req", stand_in, LlmConfig("http://localhost:1/v1", "m", ""),  # type: ignore[arg-type]
                     lambda *a: calls.append(a))
    assert calls == []


# ---- short keys -----------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["a", "abc", "12345"])
def test_short_keys_are_refused_before_sending(key):
    calls = []
    with pytest.raises(LlmError) as e:
        draft_policy("req", parse_dictionary(DICT_MD, "health"), LlmConfig("http://localhost:1/v1", "m", key),
                     lambda *a: calls.append(a))
    assert calls == [] and key not in str(e.value) or key == "a"
    with pytest.raises(LlmError):
        resolve_config("http://localhost:1/v1", "m", {"PETS_LLM_API_KEY": key})


def test_six_char_key_echo_is_screened():
    from pets_release.llm.draft import DraftRejected

    with pytest.raises(DraftRejected):
        draft_policy("req", parse_dictionary(DICT_MD, "health"), LlmConfig("http://localhost:1/v1", "m", "s3cr3t"),
                     lambda *a: _chat(dict(GOOD, recipient="x s3cr3t y")))


# ---- AC3: incomplete alignment is a failure, nothing written -----------------------------------------

SCEN = {"id": "HEALTH-S1", "dataset": "health", "recipient": "A research group", "purpose": "Analyse stays",
        "utility_requirements": ["H-U2", "H-U4"]}
FULL = dict(GOOD, purposeChecks=[{"id": "H-U2", "reason": "a"}, {"id": "H-U4", "reason": "b"}])


def _align(cli, make_kit, tmp_path, reply, use_out):
    p = FakeProvider(tmp_path / "provider", reply=reply)
    out = tmp_path / "d.json"
    try:
        kit = make_kit(scenarios=[SCEN])
        extra = ["--out", str(out)] if use_out else []
        r = cli("draft-policy", "--align-with", "HEALTH-S1", "--kit", str(kit), "--allow-network", *extra,
                env=p["env"])
    finally:
        p.close()
    return r, out


@pytest.mark.parametrize("use_out", [False, True])
def test_incomplete_alignment_exits_nonzero_and_writes_nothing(cli, make_kit, tmp_path, use_out):
    r, out = _align(cli, make_kit, tmp_path, GOOD, use_out)
    assert r.returncode == 1, r.stderr
    assert r.stdout == "" and not out.exists() and not (tmp_path / "d.json.tmp").exists()
    assert "recovered 1 of 2" in r.stderr


def test_complete_alignment_exits_zero_and_writes(cli, make_kit, tmp_path):
    r, out = _align(cli, make_kit, tmp_path, FULL, True)
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "draft"
    assert "recovered 2 of 2" in r.stderr


def test_docs_do_not_claim_exit_zero_regardless():
    doc = (Path(__file__).resolve().parents[2] / "docs" / "llm-front-end.md").read_text(encoding="utf-8")
    assert "regardless" not in doc
