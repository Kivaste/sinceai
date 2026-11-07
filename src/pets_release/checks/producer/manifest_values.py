"""``producer.manifest-source-values``: no source or released cell value in the manifest (#80, #149).

Spec #1 story 34 (the manifest itself scanned for data values) as one registered check, so the writer's gate,
the writer's verify-phase self-scan and ``verify --full`` all run the same implementation.

A hit is any source cell value (every table and column of ``context["source"]``: withheld tables and columns,
suppressed rows, raw forms of transformed columns) or released cell value of at least SCAN_MIN_LEN characters,
after case folding and whitespace collapsing, occurring as a substring of a manifest string or map KEY, at any
depth, ``contract`` included. Frequency never exempts a value. Two exemptions, both by identity:
  - a string (value or key) exactly equal to a table, file or column header name of the source or the release;
  - an item of ``contract.files[<f>].columns[<c>].params.values`` (an enum's categories) that is a value of
    column ``<c>`` of released file ``<f>``: the contract must list the released categories.

Phase ``gate``: the manifest is not assembled yet; the candidate contract (the manifest's future ``contract``) is
scanned, plus a manifest file if one is present. Phase ``verify`` (default): the manifest must exist and is
scanned whole. No usable ``source`` in the context is ``not_run`` (refuses). The record carries one violation
with a count of hit JSON paths, never a value or a path.
"""
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from pets_release.checks.records import Outcome, Violation
from pets_release.checks.registry import register

from ._common import CheckError, read_csv, release_dir

CHECK = "producer.manifest-source-values"
MANIFEST = "privacy_manifest.json"
SCAN_MIN_LEN = 6


def fold(s: str) -> str:
    """Case-folded, whitespace-collapsed form: the unit every value and manifest string is compared in."""
    return " ".join(str(s).casefold().split())


def _values(frames) -> set[str]:
    out: set[str] = set()
    for df in frames:
        for col in df.columns:
            for v in pd.unique(df[col].to_numpy(dtype=object)):
                if isinstance(v, str):
                    f = fold(v)
                    if len(f) >= SCAN_MIN_LEN:
                        out.add(f)
    return out


def _walk(node, path: tuple, out: list) -> None:
    """(path, text) for every map key and string under ``node``."""
    if isinstance(node, dict):
        for k, v in node.items():
            out.append(((*path, str(k)), str(k)))
            _walk(v, (*path, str(k)), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, (*path, i), out)
    elif isinstance(node, str):
        out.append((path, node))


def _enum_item(path: tuple, text: str, released: dict) -> bool:
    if len(path) == 8 and path[:2] == ("contract", "files") and path[3] == "columns" \
            and path[5:7] == ("params", "values") and isinstance(path[7], int):
        cells = released.get((path[2], path[4]))
        return cells is not None and text in cells
    return False


def index(values: set) -> dict:
    """{first SCAN_MIN_LEN characters: [values]}: the prefilter that keeps the scan linear in manifest text."""
    out: dict = {}
    for v in values:
        out.setdefault(v[:SCAN_MIN_LEN], []).append(v)
    return out


def occurs(idx: dict, text: str) -> bool:
    """Any indexed value (each >= SCAN_MIN_LEN long) a substring of ``text``."""
    for i in range(len(text) - SCAN_MIN_LEN + 1):
        for v in idx.get(text[i:i + SCAN_MIN_LEN], ()):
            if text.startswith(v, i):
                return True
    return False


# The source index is the expensive part (every source cell, folded); the gate runs once per suppression round
# and the self-scan again, all on the same source mapping. One entry, held by identity (the reference keeps the
# mapping alive, so its id cannot be reused while cached).
_SOURCE_CACHE: list = []


def _source_index(source: Mapping) -> tuple[dict, set]:
    if _SOURCE_CACHE and _SOURCE_CACHE[0][0] is source and _SOURCE_CACHE[0][1] == tuple(
            (k, id(df), df.shape) for k, df in source.items()):
        return _SOURCE_CACHE[0][2]
    headers = set(source) | {str(c) for df in source.values() for c in df.columns}
    entry = (index(_values(source.values())), headers)
    _SOURCE_CACHE[:] = [(source, tuple((k, id(df), df.shape) for k, df in source.items()), entry)]
    return entry


def hit_count(manifest_like: dict, source: Mapping, release_tables: Mapping) -> int:
    """Number of manifest strings/keys that carry a source or released value (see the module docstring).
    ``release_tables``: {file name: DataFrame} of the released CSVs."""
    src_idx, src_headers = _source_index(source)
    headers = src_headers | set(release_tables) \
        | {name[:-4] for name in release_tables if name.endswith(".csv")} \
        | {str(c) for df in release_tables.values() for c in df.columns}
    released = {(name, str(c)): set(df[c].tolist()) for name, df in release_tables.items() for c in df.columns}
    rel_idx = index(_values(release_tables.values()))
    texts: list = []
    _walk(manifest_like, (), texts)
    hits = 0
    for path, text in texts:
        if text in headers or _enum_item(path, text, released):
            continue
        f = fold(text)
        if len(f) >= SCAN_MIN_LEN and (occurs(src_idx, f) or occurs(rel_idx, f)):
            hits += 1
    return hits


def usable_source(context) -> bool:
    source = (context or {}).get("source")
    return isinstance(source, Mapping) and bool(source) and all(isinstance(df, pd.DataFrame)
                                                                 for df in source.values())


@register(name=CHECK, version="1.0.0", scope="producer", unit="files")
def run_manifest_source_values(release, contract, context) -> Outcome:
    context = context or {}
    if not usable_source(context):
        return Outcome.not_run()
    root = release_dir(release)
    phase = context.get("phase", "verify")
    p = root / MANIFEST
    if phase != "gate" and not p.is_file():
        return Outcome(n=1, violations=(Violation(CHECK, "manifestMissing", "high", MANIFEST, None, 1),))
    tables = {q.name: read_csv(q) for q in sorted(root.iterdir()) if q.is_file() and q.suffix.lower() == ".csv"}
    roots = []
    if phase == "gate":
        if not isinstance(contract, dict):
            raise CheckError("contract is not a mapping")
        roots.append({"contract": contract})
    if p.is_file():
        # lazy: manifest.schema imports pets_release.checks
        from pets_release.manifest.canonical import loads_strict

        try:
            manifest = loads_strict(p.read_bytes())
        except ValueError:  # #114: duplicate key, NaN/Infinity, bad JSON or bytes: never a pass
            return Outcome(n=1, violations=(Violation(CHECK, "manifestUnparseable", "high", MANIFEST, None, 1),))
        if not isinstance(manifest, dict):
            raise CheckError("manifest is not a mapping")
        roots.append(manifest)
    hits = sum(hit_count(r, context["source"], tables) for r in roots)
    out = (Violation(CHECK, "sourceValue", "high", MANIFEST, None, hits),) if hits else ()
    return Outcome(n=1, violations=out)
