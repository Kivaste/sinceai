"""Round-2 review (D31): every value that can reach the transport (body, URL, key header) is exact-type text.

A `str` subclass can override `strip`, `rstrip`, `__format__`, `__eq__` or `__hash__` and smuggle a planted value
past the screens. The call must be refused before the transport sees anything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from llm_helpers import DICT_MD

from pets_release.llm.client import LlmConfig, LlmError, draft_policy
from pets_release.llm.dictionary import DictionaryError, parse_dictionary
from pets_release.llm.prompt import build_messages
from pets_release.llm.vocabulary import vocabulary_for

PLANT = "planted.person@example.org 040-1234567"
GOOD = {
    "recipient": "University research group",
    "trustLevel": "controlled_research",
    "purposeChecks": [{"id": "H-U2", "reason": "length of stay"}],
    "fieldsNeeded": [{"table": "ed_visits", "column": "los_minutes", "detail": "exact", "reason": "stay"}],
}
REFUSED = (LlmError, DictionaryError, TypeError)


def _chat(obj):
    return json.dumps({"choices": [{"message": {"content": json.dumps(obj)}}]}).encode()


class _Recorder:
    """Network edge only: records what would be sent."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, body, key, timeout):
        self.calls.append((url, body, key))
        return _chat(GOOD)

    def leaked(self) -> bool:
        return any(PLANT in u or PLANT.encode() in b or PLANT in k for u, b, k in self.calls)


class SneakyRequest(str):
    """Looks harmless to isinstance/strip; formats as the plant."""

    def strip(self, *a):
        return SneakyRequest(str.__str__(self))

    def __format__(self, spec):
        return PLANT

    def __str__(self):
        return PLANT


class SneakyEndpoint(str):
    def rstrip(self, *a):
        return "http://localhost:1/" + PLANT


class SneakyText(str):
    def __str__(self):
        return PLANT

    def __format__(self, spec):
        return PLANT


class EqualsAnything(str):
    """Passes `in ROLES` / `in SUBTYPES` by equality, but its own text is the plant."""

    def __eq__(self, other):
        return True

    def __hash__(self):
        return hash("record_key")


def _dict():
    return parse_dictionary(DICT_MD, "health")


def _cfg(endpoint="http://localhost:1/v1", model="m", key=""):
    return LlmConfig(endpoint, model, key)


def _run(request="Researchers want length of stay", dictionary=None, config=None):
    t = _Recorder()
    err = None
    try:
        draft_policy(request, dictionary or _dict(), config or _cfg(), t)
    except Exception as e:  # noqa: BLE001 - checked below, after the wire
        err = e
    assert t.calls == [], f"transport was called; plant on the wire: {t.leaked()}"
    assert isinstance(err, REFUSED), f"not refused: {type(err).__name__}"
    return t


def test_control_plain_inputs_reach_transport_without_plant():
    t = _Recorder()
    draft_policy("Researchers want length of stay", _dict(), _cfg(), t)
    assert len(t.calls) == 1 and not t.leaked()


def test_request_str_subclass_is_refused_before_transport():
    t = _run(request=SneakyRequest("Researchers want length of stay"))
    assert t.calls == []


def test_build_messages_refuses_request_str_subclass():
    with pytest.raises(REFUSED):
        build_messages(SneakyRequest("req"), _dict(), vocabulary_for("health"))


def test_endpoint_str_subclass_is_refused_before_transport():
    t = _run(config=_cfg(endpoint=SneakyEndpoint("http://localhost:1/v1")))
    assert t.calls == []


@pytest.mark.parametrize("model", [{"x": PLANT}, [PLANT], SneakyText("m"), 7])
def test_model_not_exact_text_is_refused_before_transport(model):
    t = _run(config=_cfg(model=model))
    assert t.calls == []


def test_api_key_str_subclass_is_refused_before_transport():
    t = _run(config=_cfg(key=SneakyText("abcdefgh")))
    assert t.calls == []


def test_config_subclass_is_refused_before_transport():
    class Shifty(LlmConfig):
        pass

    t = _run(config=Shifty("http://localhost:1/v1", "m", ""))
    assert t.calls == []


@pytest.mark.parametrize("field", ["role", "subtype", "name"])
def test_dictionary_column_str_subclass_is_refused_before_transport(field):
    d = _dict()
    col = d.tables[0].columns[0]
    object.__setattr__(col, field, EqualsAnything(PLANT if field != "name" else "visit_id"))
    t = _run(dictionary=d)
    assert t.calls == []


def test_dictionary_table_and_dataset_str_subclass_are_refused_before_transport():
    d = _dict()
    object.__setattr__(d.tables[0], "name", SneakyText("ed_visits"))
    assert _run(dictionary=d).calls == []
    d2 = _dict()
    object.__setattr__(d2, "dataset", SneakyText("health"))
    assert _run(dictionary=d2).calls == []
