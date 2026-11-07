"""Provider config, request screening and the OpenAI-compatible chat-completions exchange."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from helpers import DICT_MD  # noqa: E402
from pets_release.llm.client import LlmConfig, LlmError, draft_policy, resolve_config, screen_request
from pets_release.llm.dictionary import parse_dictionary

GOOD = {
    "recipient": "University research group",
    "trustLevel": "controlled_research",
    "purposeChecks": [{"id": "H-U2", "reason": "length of stay"}],
    "fieldsNeeded": [{"table": "ed_visits", "column": "los_minutes", "detail": "exact", "reason": "outcome"}],
}
CFG = LlmConfig(endpoint="http://localhost:11434/v1", model="local-model", api_key="sekret-key-123")


class FakeTransport:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, url, body, api_key, timeout):
        self.calls.append((url, json.loads(body), api_key))
        return self.reply if isinstance(self.reply, bytes) else json.dumps(self.reply).encode()


def _chat(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _run(transport, request="Researchers want length of stay by triage"):
    return draft_policy(request, parse_dictionary(DICT_MD, "health"), CFG, transport)


def test_exchange_posts_to_chat_completions_and_returns_a_draft():
    t = FakeTransport(_chat(json.dumps(GOOD)))
    draft = _run(t)
    (url, payload, key), = t.calls
    assert url == "http://localhost:11434/v1/chat/completions"
    assert payload["model"] == "local-model" and payload["temperature"] == 0
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert key == "sekret-key-123"
    assert "sekret-key-123" not in json.dumps(payload)
    assert draft["status"] == "draft" and draft["model"] == "local-model"


def test_endpoint_already_ending_in_chat_completions_is_kept():
    t = FakeTransport(_chat(json.dumps(GOOD)))
    cfg = LlmConfig("https://api.example.test/v1/chat/completions", "m", "")
    draft_policy("req", parse_dictionary(DICT_MD, "health"), cfg, t)
    assert t.calls[0][0] == "https://api.example.test/v1/chat/completions"


@pytest.mark.parametrize("reply", [b"not json", {"choices": []}, {"x": 1}, _chat(None), _chat(5), _chat("")])
def test_malformed_provider_reply_fails_closed(reply):
    with pytest.raises(LlmError):
        _run(FakeTransport(reply))


def test_transport_failure_is_reported_without_the_key():
    def boom(url, body, api_key, timeout):
        raise OSError(f"connect failed for {api_key}")

    with pytest.raises(LlmError) as e:
        _run(boom)
    assert "sekret-key-123" not in str(e.value)


def test_model_output_outside_the_vocabulary_is_rejected():
    bad = dict(GOOD, purposeChecks=[{"id": "H-U99", "reason": "x"}])
    with pytest.raises(Exception) as e:
        _run(FakeTransport(_chat(json.dumps(bad))))
    assert "H-U99" not in str(e.value)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "mail me at someone@example.org", "my id is 010170-123A", "card 4111111111111111", "x" * 5000],
)
def test_request_screen_refuses_values_and_oversize(text):
    with pytest.raises(LlmError):
        screen_request(text)


def test_request_screen_accepts_plain_language():
    assert screen_request("  Researchers want length of stay by triage level.  ") == (
        "Researchers want length of stay by triage level."
    )


def test_config_precedence_flags_over_env_and_missing_is_an_error():
    env = {"PETS_LLM_ENDPOINT": "http://e/v1", "PETS_LLM_MODEL": "em", "PETS_LLM_API_KEY": "k"}
    cfg = resolve_config(None, None, env)
    assert (cfg.endpoint, cfg.model, cfg.api_key) == ("http://e/v1", "em", "k")
    cfg = resolve_config("http://flag/v1", "fm", env)
    assert (cfg.endpoint, cfg.model) == ("http://flag/v1", "fm")
    with pytest.raises(LlmError):
        resolve_config(None, None, {})
    with pytest.raises(LlmError):
        resolve_config("ftp://x/v1", "m", {})
    assert resolve_config("http://e/v1", "m", {}).api_key == ""  # local servers may need no key
