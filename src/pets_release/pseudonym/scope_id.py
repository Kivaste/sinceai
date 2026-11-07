"""Deterministic release-scope ID.

first 16 hex of SHA-256(canonical JSON of
{"inputs": {table: sha256}, "recipient": str|null, "scenario": str,
 "toolRevision": str})
Canonical JSON: sorted keys, separators (",", ":"), UTF-8, no ASCII escaping.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


# TODO(merge): switch to ticket 02's canonical JSON in pets_release.manifest
# once it lands; tests/pseudonym/test_keys.py pins these exact bytes.
def _canonical(obj: object) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def release_scope_id(
    *,
    scenario: str,
    recipient: str | None,
    input_digests: Mapping[str, str],
    tool_revision: str,
) -> str:
    if not isinstance(scenario, str) or not scenario:
        raise ValueError("scenario must be a non-empty string")
    if recipient is not None and (not isinstance(recipient, str) or not recipient):
        raise ValueError("recipient must be a non-empty string or None")
    if not isinstance(tool_revision, str) or not tool_revision:
        raise ValueError("tool revision must be a non-empty string")
    if not input_digests:
        raise ValueError("at least one input digest is required")
    inputs: dict[str, str] = {}
    for table, digest in input_digests.items():
        if not isinstance(table, str) or not table:
            raise ValueError("input table names must be non-empty strings")
        if not isinstance(digest, str) or not _SHA256_HEX.fullmatch(digest):
            raise ValueError("input digests must be lowercase 64-hex SHA-256")
        inputs[table] = digest
    payload = {
        "inputs": inputs,
        "recipient": recipient,
        "scenario": scenario,
        "toolRevision": tool_revision,
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()[:16]
