"""Canonical JSON: sorted keys, separators `,` and `:`, UTF-8, no NaN/Infinity, no trailing newline."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _check_keys(obj: Any) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be str")
            _check_keys(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _check_keys(item)


def canonical_bytes(obj: Any) -> bytes:
    """Serialise ``obj`` to canonical JSON bytes. Raises ValueError on NaN/Infinity, TypeError on non-str keys."""
    _check_keys(obj)
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return text.encode("utf-8")


def canonical_digest(obj: Any) -> str:
    """SHA-256 hex digest of ``canonical_bytes(obj)``."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON object key")
        out[key] = value
    return out


def _no_constant(_name: str) -> Any:
    raise ValueError("non-finite JSON number constant")


def loads_strict(raw: bytes | str, *, numbers_as_text: bool = False) -> Any:
    """Parse JSON, rejecting duplicate keys (any depth) and NaN/Infinity. Raises ValueError (JSONDecodeError and
    UnicodeDecodeError included). ``numbers_as_text`` keeps every number as its exact JSON text (for scanners).
    The one manifest loader (#114): every production reader of a manifest parses through here."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    extra = {"parse_int": str, "parse_float": str} if numbers_as_text else {}
    return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_no_constant, **extra)
