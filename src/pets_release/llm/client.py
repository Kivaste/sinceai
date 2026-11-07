"""OpenAI-compatible chat-completions client with an injected transport.

The transport is `(url, body_bytes, api_key, timeout) -> response_bytes`; it is the only thing that
touches the network. The CLI supplies a subprocess transport (`transport.py`); tests supply fakes.
Errors never carry the API key, the request text or model output.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from pets_release.llm.dictionary import DataDictionary
from pets_release.llm.draft import DraftRejected, build_draft, parse_model_output
from pets_release.llm.prompt import build_messages
from pets_release.llm.screen import has_credential, has_value_shape
from pets_release.llm.vocabulary import vocabulary_for

MAX_REQUEST = 2000
MAX_REPLY_BYTES = 262_144  # whole HTTP body; the sender enforces the same cap before buffering
MAX_CONTENT_CHARS = 65_536  # model text, before JSON parsing
TIMEOUT_S = 120
Transport = Callable[[str, bytes, str, float], bytes]


class LlmError(Exception):
    """Configuration, transport or reply problem. The message is content-free."""


@dataclass(frozen=True)
class LlmConfig:
    endpoint: str
    model: str
    api_key: str = ""

    def __repr__(self) -> str:  # never print the key
        return f"LlmConfig(endpoint={self.endpoint!r}, model={self.model!r}, api_key=<hidden>)"


def resolve_config(endpoint: str | None, model: str | None, env: Mapping[str, str]) -> LlmConfig:
    endpoint = endpoint or env.get("PETS_LLM_ENDPOINT", "")
    model = model or env.get("PETS_LLM_MODEL", "")
    if not endpoint:
        raise LlmError("no endpoint: pass --endpoint or set PETS_LLM_ENDPOINT")
    if not model:
        raise LlmError("no model: pass --model or set PETS_LLM_MODEL")
    if urlparse(endpoint).scheme not in ("http", "https") or not urlparse(endpoint).netloc:
        raise LlmError("endpoint must be an http or https URL")
    return LlmConfig(endpoint, model, env.get("PETS_LLM_API_KEY", ""))


def screen_request(text: str) -> str:
    """The request must be plain language: no identifier-shaped values, bounded length."""
    text = text.strip() if isinstance(text, str) else ""
    if not text:
        raise LlmError("the data request is empty")
    if len(text) > MAX_REQUEST:
        raise LlmError(f"the data request is longer than {MAX_REQUEST} characters")
    if has_value_shape(text):
        raise LlmError("the data request contains a value-shaped string (email, ID or long number); remove it")
    return text


def _url(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def draft_policy(
    request: str, dictionary: DataDictionary, config: LlmConfig, transport: Transport
) -> dict:
    """Request text + typed dictionary in, validated DRAFT policy out. Raises LlmError or DraftRejected."""
    request = screen_request(request)
    messages = build_messages(request, dictionary, vocabulary_for(dictionary.dataset))
    body = json.dumps(
        {"model": config.model, "messages": messages, "temperature": 0}, sort_keys=True
    ).encode("utf-8")
    try:
        raw = transport(_url(config.endpoint), body, config.api_key, TIMEOUT_S)
    except Exception:  # noqa: BLE001 - the exception text could echo the key or the endpoint
        raise LlmError("the provider request failed") from None
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_REPLY_BYTES:
        raise LlmError("the provider reply is missing or larger than the size limit")
    try:
        content = json.loads(raw)["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LlmError("the provider reply is not a chat-completions response") from None
    if not isinstance(content, str) or not content.strip():
        raise LlmError("the provider reply has no text content")
    if len(content) > MAX_CONTENT_CHARS:
        raise LlmError("the model text is larger than the size limit")
    draft = build_draft(parse_model_output(content), dictionary, request=request, model=config.model)
    model_fields = {k: v for k, v in draft.items() if k != "requestSha256"}  # the digest is ours, not the model's
    if has_credential(list(_strings(model_fields)), config.api_key):
        raise DraftRejected("the draft contains a credential or the API key")
    return draft


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)
