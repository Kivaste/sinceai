"""``producer.manifest-source-values``: no source or released cell value in the manifest (#80, #149).

Spec #1 story 34 (the manifest itself scanned for data values) as one registered check, so the writer's gate,
the writer's verify-phase self-scan and ``verify --full`` all run the same implementation.

A hit is any source cell value (every table and column of ``context["source"]``: withheld tables and columns,
suppressed rows, raw forms of transformed columns) or released cell value of at least SCAN_MIN_LEN characters,
after case folding and whitespace collapsing, occurring as a substring of a manifest string or map KEY, at any
depth, ``contract`` included. Frequency never exempts a value. Two exemptions, both by identity AND location:
  - a string exactly equal to a table, file or column header name of the source or the release, only at the
    structural header paths ``HEADER_KEY_PATHS`` (map keys) and ``HEADER_VALUE_PATHS`` (values); elsewhere a
    header-equal string is scanned (#149 r2);
  - deliberately beyond "header names only": an item of ``contract.files[<f>].columns[<c>].params.values`` of a
    column whose form is ``enum``, that is a cell of column ``<c>`` of released file ``<f>``. An enum contract must
    list its released categories, which are legitimately released (and usually source) values.

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


_ANY = object()  # path wildcard: any map key or list index
_NAME = ("column", "table")
_PARAM_NAMES = ("derived_from", "output", "ref_column")  # params whose value is a column name
# Structural header locations, by JSON path (#149 r2). Only here may a string (the KEY itself, or the VALUE) be
# a table, file or column name; a header-equal string anywhere else is scanned like any other text.
HEADER_KEY_PATHS = (
    ("bindings", "files", _ANY), ("bindings", "inputs", _ANY), ("contract", "files", _ANY),
    ("contract", "files", _ANY, "columns", _ANY),
)
HEADER_VALUE_PATHS = (
    *(("contract", "files", _ANY, "columns", _ANY, "params", p) for p in _PARAM_NAMES),
    ("contract", "files", _ANY, "required", _ANY),
    *(("contract", "qi", _ANY, k) for k in (*_NAME, "derived_from")),
    *(("contract", "tokens", _ANY, k) for k in _NAME),
    *(("fieldJustifications", _ANY, k) for k in (*_NAME, "outputColumn")),
    *(("inventory", _ANY, k) for k in _NAME),
    *(("pets", _ANY, k) for k in _NAME),
    *(("pets", _ANY, "params", p) for p in _PARAM_NAMES),
    *(("sacrifices", _ANY, "rungStep", k) for k in _NAME),
    # #146 measured.kSets: the schema's name fields only; its reason/source free text stays scanned (#149 r3)
    *(("measured", "kSets", "sets", _ANY, "qi", _ANY, k) for k in (*_NAME, "derived_from")),
    *(("measured", "kSets", "withheld", _ANY, k) for k in _NAME),
)


def _matches(path: tuple, patterns) -> bool:
    return any(len(p) == len(path) and all(a is _ANY or a == b for a, b in zip(p, path)) for p in patterns)


def _walk(node, path: tuple, out: list) -> None:
    """(path, text, is_key) for every map key and string under ``node``; a key's path ends at the key."""
    if isinstance(node, dict):
        for k, v in node.items():
            out.append(((*path, str(k)), str(k), True))
            _walk(v, (*path, str(k)), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, (*path, i), out)
    elif isinstance(node, str):
        out.append((path, node, False))


def _enum_columns(manifest_like: dict) -> set:
    """{(file, column)} whose contract form is ``enum``."""
    files = (manifest_like.get("contract") or {}).get("files") if isinstance(manifest_like, dict) else None
    out = set()
    if isinstance(files, dict):
        for f, spec in files.items():
            cols = spec.get("columns") if isinstance(spec, dict) else None
            if isinstance(cols, dict):
                out |= {(f, c) for c, col in cols.items() if isinstance(col, dict) and col.get("form") == "enum"}
    return out


def _enum_item(path: tuple, text: str, released: dict, enums: set) -> bool:
    """A deliberate exception beyond "exact header names only" (#149 r2), bound to path, form and column: an
    ``enum`` column's contract must list its categories, which ARE released (and usually source) values. Only an
    item at ``contract.files[f].columns[c].params.values[i]`` of a column whose form is ``enum`` and that is a
    cell of column ``c`` of released file ``f`` is exempt; the same text anywhere else is scanned."""
    if len(path) == 8 and path[:2] == ("contract", "files") and path[3] == "columns" \
            and path[5:7] == ("params", "values") and isinstance(path[7], int) and (path[2], path[4]) in enums:
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


def hit_count(manifest_like: dict, source: Mapping, release_tables: Mapping) -> int:
    """Number of manifest strings/keys that carry a source or released value (see the module docstring).
    ``release_tables``: {file name: DataFrame} of the released CSVs. The source index is rebuilt on every call
    (#149 r2: no cache, so an in-place source change is never answered from a stale index; ~1-3 s per call)."""
    headers = set(source) | {str(c) for df in source.values() for c in df.columns} | set(release_tables) \
        | {name[:-4] for name in release_tables if name.endswith(".csv")} \
        | {str(c) for df in release_tables.values() for c in df.columns}
    released = {(name, str(c)): set(df[c].tolist()) for name, df in release_tables.items() for c in df.columns}
    enums = _enum_columns(manifest_like)
    idx = index(_values(source.values()) | _values(release_tables.values()))
    texts: list = []
    _walk(manifest_like, (), texts)
    hits = 0
    for path, text, is_key in texts:
        if text in headers and _matches(path, HEADER_KEY_PATHS if is_key else HEADER_VALUE_PATHS):
            continue
        if not is_key and _enum_item(path, text, released, enums):
            continue
        f = fold(text)
        if len(f) >= SCAN_MIN_LEN and occurs(idx, f):
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
