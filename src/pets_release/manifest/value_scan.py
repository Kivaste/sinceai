"""Identifier-shape scan over the manifest itself (#61). Error codes carry a JSON path and a label, never a value.

The release rescans read CSV cells only, and the producer value checks look for known source values, so a new
identifier typed into a narrative string would otherwise pass every gate and reach the dashboard. This rule runs
the same independent detectors as the release rescans (``checks.cells._validators``, via ``labels.LABEL_CHECKS``)
over every manifest string, every map key and every number inside a ``params`` map. It is part of manifest
validation, so it runs after assembly in the writer, in the writer's self-scan, at step 1 of both verify tiers
and in the dashboard.

Skipped (pinned metadata, each schema-constrained to a digest/name/timestamp pattern): ``bindings`` (file/input/
lexicon/contract digests, tool revision, check versions), ``signature`` (alg, key ID, HMAC), and
``release.releaseScopeId`` / ``release.created``. Nothing else is exempt: a hit anywhere else is an error, high
or low severity alike (fail closed).
"""
from __future__ import annotations

import json
from typing import Any

SKIP_PATHS = frozenset({("bindings",), ("signature",), ("release", "releaseScopeId"), ("release", "created")})


def _detectors():
    from pets_release.checks.cells.labels import LABEL_CHECKS

    return sorted(LABEL_CHECKS.values())


def _skipped(path: tuple) -> bool:
    return any(tuple(path[: len(s)]) == s for s in SKIP_PATHS)


def _texts(node: Any, path: tuple, out: list) -> None:
    """(path, text) for every string, map key and params number under ``node``, minus SKIP_PATHS."""
    if _skipped(path):
        return
    if isinstance(node, dict):
        for k, v in node.items():
            sub = (*path, str(k))
            if not _skipped(sub):
                out.append((sub, str(k)))
            _texts(v, sub, out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _texts(v, (*path, i), out)
    elif isinstance(node, str):
        out.append((path, node))
    elif isinstance(node, (int, float)) and not isinstance(node, bool) and "params" in path:
        out.append((path, json.dumps(node)))


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
