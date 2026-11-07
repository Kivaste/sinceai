"""Review round 1: metadata value screen, credential echo, response size cap."""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fake_provider import FakeProvider
from llm_helpers import DICT_MD

from pets_release.llm.client import LlmConfig, LlmError, draft_policy
from pets_release.llm.dictionary import ColumnInfo, DictionaryError, TableInfo, parse_dictionary
from pets_release.llm.draft import DraftRejected
from pets_release.llm.prompt import build_messages
from pets_release.llm.vocabulary import vocabulary_for

KEY = "sekret-key-0123456789"
GOOD = {
    "recipient": "University research group",
    "trustLevel": "controlled_research",
    "purposeChecks": [{"id": "H-U2", "reason": "length of stay"}],
    "fieldsNeeded": [{"table": "ed_visits", "column": "when", "detail": "exact", "reason": "time"}],
}
PLANTS = {
    "email": "someone@example.org",
    "hetu": "010170-123A",
    "digits": "123456789012",
    "iban": "FI2112345600000785",
    "phone": "+358401234567",
    "url": "https://leak.example.org/x",
}


def _md(role="quasi_identifier", subtype="DATE", name="when", desc="Date of visit"):
    return (
        "## health\n\n### health / ed_visits\n\n| column | role | subtype | Art. 9 | description |\n"
        f"|---|---|---|---|---|\n| `{name}` | {role} | {subtype} |  | {desc} |\n"
    )


@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_value_shaped_description_is_excluded_from_the_prompt(plant):
    d = parse_dictionary(_md(desc=f"Sample {PLANTS[plant]} here"), "health")
    text = json.dumps(build_messages("req", d, vocabulary_for("health")))
    assert PLANTS[plant] not in text and "Sample" not in text


def test_clean_descriptions_are_not_sent_either():
    d = parse_dictionary(_md(desc="Visit identifier ED25-NNNNNN or AU-<base>-NN"), "health")
    text = json.dumps(build_messages("req", d, vocabulary_for("health")))
    assert "Visit identifier" not in text and "when" in text


@pytest.mark.parametrize(
    "kw",
    [
        {"role": "someone@example.org"},
        {"role": "not_a_role"},
        {"subtype": "010170-123A"},
        {"subtype": "MADE_UP_TYPE"},
        {"name": "someone@example.org"},
        {"name": "has space"},
        {"name": "x123456789012"},
    ],
)
def test_role_subtype_and_names_are_a_closed_allowlist(kw):
    with pytest.raises(DictionaryError) as e:
        parse_dictionary(_md(**kw), "health")
    assert "example.org" not in str(e.value) and "123A" not in str(e.value)


def test_directly_built_dictionary_objects_are_validated_too():
    with pytest.raises(DictionaryError):
        ColumnInfo("c", "bad role", "DATE")
    with pytest.raises(DictionaryError):
        TableInfo("t@x.org", (ColumnInfo("c", "record_key", "RECORD_ID"),))


# ---- credential echo ------------------------------------------------------------------------------

CFG = LlmConfig("http://localhost:1/v1", "m", KEY)


def _chat(obj):
    return json.dumps({"choices": [{"message": {"content": json.dumps(obj)}}]}).encode()


@pytest.mark.parametrize(
    "echo",
    [
        KEY,
        base64.b64encode(KEY.encode()).decode(),
        KEY.encode().hex(),
        "prefix-" + KEY + "-suffix",
        "sk-abcdefghijklmnopqrstuv",
        "Bearer abcdefghijkl",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghij",
    ],
)
def test_credentials_in_a_draft_are_rejected(echo):
    reply = dict(GOOD, recipient=echo)
    with pytest.raises(DraftRejected) as e:
        draft_policy("req", parse_dictionary(DICT_MD, "health"), CFG, lambda *a: _chat(reply))
    assert KEY not in str(e.value) and echo not in str(e.value)


def test_credential_in_a_reason_is_rejected_too():
    reply = json.loads(json.dumps(GOOD))
    reply["fieldsNeeded"][0]["reason"] = KEY
    with pytest.raises(DraftRejected):
        draft_policy("req", parse_dictionary(DICT_MD, "health"), CFG, lambda *a: _chat(reply))


def test_oversized_provider_reply_is_rejected_before_parsing():
    big = b" " * 2_000_000 + _chat(GOOD)
    with pytest.raises(LlmError):
        draft_policy("req", parse_dictionary(DICT_MD, "health"), CFG, lambda *a: big)


def test_oversized_model_content_is_rejected():
    reply = dict(GOOD, recipient="x" * 10)
    raw = json.dumps({"choices": [{"message": {"content": " " * 200_000 + json.dumps(reply)}}]}).encode()
    with pytest.raises(LlmError):
        draft_policy("req", parse_dictionary(DICT_MD, "health"), CFG, lambda *a: raw)


# ---- real CLI ---------------------------------------------------------------------------------------


@pytest.fixture
def server(tmp_path):
    p = FakeProvider(tmp_path / "provider", api_key=KEY, reply=GOOD)
    yield p
    p.close()


ARGS = ["draft-policy", "--request", "Researchers want visit times", "--dataset", "health", "--allow-network"]


def _kit(make_kit, **kw):
    return str(make_kit(dictionary="# Data dictionary\n\n" + _md(**kw)))


def test_cli_planted_description_never_reaches_the_wire(cli, make_kit, server):
    kit = _kit(make_kit, desc=f"Sample {PLANTS['email']} {PLANTS['hetu']}")
    r = cli(*ARGS, "--kit", kit, env=server["env"])
    assert r.returncode == 0, r.stderr
    wire = server["bodies"][0].decode()
    assert "when" in wire
    for v in PLANTS.values():
        assert v not in wire


@pytest.mark.parametrize("kw", [{"role": PLANTS["email"]}, {"subtype": PLANTS["hetu"]}, {"name": PLANTS["email"]}])
def test_cli_planted_role_subtype_or_name_transmits_nothing(cli, make_kit, server, kw):
    r = cli(*ARGS, "--kit", _kit(make_kit, **kw), env=server["env"])
    assert r.returncode == 2
    assert server["bodies"] == []
    assert PLANTS["email"] not in r.stdout + r.stderr


@pytest.mark.parametrize("use_out", [False, True])
def test_cli_key_echoed_by_the_provider_is_refused(cli, make_kit, server, tmp_path, use_out):
    server["reply"] = dict(GOOD, recipient=KEY)
    out = tmp_path / "d.json"
    extra = ["--out", str(out)] if use_out else []
    r = cli(*ARGS, "--kit", str(make_kit()), *extra, env=server["env"])
    assert r.returncode == 1
    assert KEY not in r.stdout + r.stderr
    assert r.stdout == "" and not out.exists()


def test_cli_oversized_reply_is_refused_and_nothing_is_written(cli, make_kit, server, tmp_path):
    server["mode"] = "big"
    out = tmp_path / "d.json"
    r = cli(*ARGS, "--kit", str(make_kit()), "--out", str(out), env=server["env"])
    assert r.returncode == 2
    assert r.stdout == "" and not out.exists()
