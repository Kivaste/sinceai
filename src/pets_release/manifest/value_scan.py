"""Identifier-shape scan over the manifest itself (#61). Error codes carry a JSON path and a label, never a value.

The release rescans read CSV cells only, and the producer value checks look for known source values, so a new
identifier typed into the manifest would otherwise pass every gate and reach the dashboard. This rule runs the
same independent detectors as the release rescans (``checks.cells._validators``, via ``labels.LABEL_CHECKS``)
over every manifest string, every map key (at any depth, ``bindings`` and ``signature`` included) and every
number (as its exact JSON text: counts, scores, parameters alike). It is part of manifest validation, so it runs
after assembly in the writer, in the writer's self-scan, at step 1 of both verify tiers and in the dashboard.

Exempt: only the pattern-locked digest/HMAC/timestamp VALUES listed in ``EXEMPT_VALUES``, and only when the value
fully matches its pattern and is not all digits (an all-digit "hex" value is scanned like any other text). Keys
under those maps (file, table, lexicon, check names) and ``signature.keyId`` are never exempt. A hit anywhere
else is an error, high or low severity alike (fail closed).
"""
from __future__ import annotations

import json
import re
from typing import Any

_SHA256 = re.compile(r"[0-9a-f]{64}")
_ANY = object()  # path wildcard: any map key
EXEMPT_VALUES = (
    (("bindings", "files", _ANY), _SHA256),
    (("bindings", "inputs", _ANY), _SHA256),
    (("bindings", "lexiconDigests", _ANY), _SHA256),
    (("bindings", "contractDigest"), _SHA256),
    (("bindings", "toolRevision"), re.compile(r"[0-9a-f]{40}")),
    (("signature", "value"), _SHA256),
    (("release", "releaseScopeId"), re.compile(r"[0-9a-f]{16}")),
    (("release", "created"), re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")),
)


def _detectors():
    from pets_release.checks.cells.labels import LABEL_CHECKS

    return sorted(LABEL_CHECKS.values())


def _exempt(path: tuple, value: str) -> bool:
    if value.isdigit():
        return False
    for pat, rx in EXEMPT_VALUES:
        if len(pat) == len(path) and all(p is _ANY or p == q for p, q in zip(pat, path)):
            return bool(rx.fullmatch(value))
    return False


def _texts(node: Any, path: tuple, out: list) -> None:
    """(path, text) for every key, string and number under ``node``, minus the exempt digest values."""
    if isinstance(node, dict):
        for k, v in node.items():
            sub = (*path, str(k))
            out.append((sub, str(k)))
            _texts(v, sub, out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _texts(v, (*path, i), out)
    elif isinstance(node, str):
        if not _exempt(path, node):
            out.append((path, node))
    elif isinstance(node, bool) or node is None:
        return
    elif isinstance(node, (int, float)):
        out.append((path, json.dumps(node)))  # the exact JSON text the canonical manifest carries
    else:
        out.append((path, str(node)))  # not JSON-native: scanned as text (schema validation rejects it anyway)


def identifier_shape_errors(manifest: Any, fmt) -> list[str]:
    """``"<path>: identifier-shape:<LABEL>"`` for every detector hit; ``fmt`` renders a content-free path."""
    texts: list = []
    _texts(manifest, (), texts)
    errs = set()
    detectors = _detectors()
    for path, text in texts:
        for label, finder in detectors:
            high, low = finder(text)
            if high or low:
                errs.add(f"{fmt(list(path))}: identifier-shape:{label}")
    return sorted(errs)
