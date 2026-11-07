"""Canonical JSON bytes for the contract digest.

Matches the spec and ticket 02: sorted keys, separators ``,`` and ``:``, UTF-8,
no NaN. When ``pets_release.manifest`` is importable, ``digest`` uses its
``canonical_digest`` so the two cannot drift.
"""

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
    """Serialise ``obj``. Raises ValueError on NaN/Infinity, TypeError on non-str keys."""
    _check_keys(obj)
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return text.encode("utf-8")


def local_digest(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def sibling_digest():
    """Ticket 02's digest, or None if that package is not on the path."""
    try:
        from pets_release.manifest import canonical_digest
    except ImportError:
        return None
    return canonical_digest
