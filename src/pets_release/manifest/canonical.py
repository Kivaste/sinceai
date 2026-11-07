"""Canonical JSON: sorted keys, separators `,` and `:`, UTF-8, no NaN/Infinity, no trailing newline."""

from __future__ import annotations

import hashlib
import json
from typing import Any

# The one strict loader (#114) lives in the stdlib-only leaf ``pets_release.strict_json`` so scorer modules can use
# it without reaching pipeline modules (fu85); re-exported here for every existing manifest-side reader.
from pets_release.strict_json import loads_strict

__all__ = ["canonical_bytes", "canonical_digest", "loads_strict"]


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

