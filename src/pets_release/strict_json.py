"""Strict JSON parsing (#114, #131): duplicate keys at any depth and NaN/Infinity refuse.

A leaf module with stdlib imports only, so scorer modules (kiteval) can parse strictly without reaching pipeline
modules (fu85 scorer isolation). ``pets_release.manifest.canonical`` re-exports ``loads_strict`` from here.
"""

from __future__ import annotations

import json
from typing import Any


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
    The one strict loader (#114): every production reader of an external JSON record parses through here."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    extra = {"parse_int": str, "parse_float": str} if numbers_as_text else {}
    return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_no_constant, **extra)
