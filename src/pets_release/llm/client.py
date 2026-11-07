"""OpenAI-compatible chat-completions client with an injected transport.

The transport is `(url, body_bytes, api_key, timeout) -> response_bytes`; it is the only thing that
touches the network. The CLI supplies a subprocess transport (`transport.py`); tests supply fakes.
Errors never carry the API key, the request text or model output.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from pets_release.llm.dictionary import DataDictionary
from pets_release.llm.draft import build_draft, parse_model_output
from pets_release.llm.prompt import build_messages
from pets_release.llm.vocabulary import vocabulary_for

MAX_REQUEST = 2000
TIMEOUT_S = 120
Transport = Callable[[str, bytes, str, float], bytes]

_VALUE_SHAPES = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"\b\d{6}[-+A-Fa-f]\d{3}[0-9A-Za-z]\b"),  # Finnish personal identity code shape
    re.compile(r"\d{9,}"),  # long digit run (phone, card, account)
    re.compile(r"\d(?:[ -]?\d){11,}"),  # spaced or dashed digit run
)


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
    if any(p.search(text) for p in _VALUE_SHAPES):
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
    try:
        content = json.loads(raw)["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LlmError("the provider reply is not a chat-completions response") from None
    if not isinstance(content, str) or not content.strip():
        raise LlmError("the provider reply has no text content")
    return build_draft(parse_model_output(content), dictionary, request=request, model=config.model)
