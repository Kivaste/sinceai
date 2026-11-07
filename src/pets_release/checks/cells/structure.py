"""Structural release checks: files, columns, forms, empty tables, row maps, per-file digests."""
from __future__ import annotations

import re

import numpy as np

from pets_release.checks.cells.common import contract_files
from pets_release.checks.records import Outcome, Violation, locations
from pets_release.checks.registry import register
from pets_release.checks.release import MANIFEST

ROWMAP_COLUMNS = {"protected_row", "original_record_id"}


@register(name="contractFiles", version="1", scope="release", unit="files")
def contract_files_check(release, contract, context):
    files = contract_files(contract)
    allowed = set(files) | {MANIFEST}
    out = []
    for e in release.entries:
        if e not in allowed or not (release.path / e).is_file():
            out.append(Violation("contractFiles", "unexpectedFile", "high", e, None, 1))
    for f in sorted(files):
        if f not in release.entries:
            out.append(Violation("contractFiles", "missingFile", "high", f, None, 1))
    return Outcome(n=len(release.entries), violations=tuple(out))


@register(name="rowMaps", version="1", scope="release", unit="files")
def row_maps_check(release, contract, context):
    out = []
    for e in release.entries:
        if "rowmap" in e.lower().replace("_", "").replace("-", ""):
            out.append(Violation("rowMaps", "rowMapFile", "high", e, None, 1))
    for f in release.csv_files:
        for col in release.table(f).header:
            if col.strip().lower() in ROWMAP_COLUMNS:
                out.append(Violation("rowMaps", "rowMapColumn", "high", f, col, 1))
    return Outcome(n=len(release.entries), violations=tuple(out))


@register(name="emptyTables", version="1", scope="release", unit="files")
def empty_tables_check(release, contract, context):
    out = [Violation("emptyTables", "emptyTable", "high", f, None, 1)
           for f in release.csv_files if len(release.table(f).frame) == 0]
    return Outcome(n=len(release.csv_files), violations=tuple(out))


@register(name="contractColumns", version="1", scope="release", unit="files")
def contract_columns_check(release, contract, context):
    files = contract_files(contract)
    out = []
    n = 0
    for f in release.csv_files:
        if f not in files:
            continue
        n += 1
        spec = files[f]
        allowed = set(spec["columns"])
        required = list(spec.get("required", []))
        if not set(required) <= allowed:
            raise ValueError("contract requires an undeclared column")
        header = release.table(f).header
        seen = set()
        for col in header:
            if col in seen:
                out.append(Violation("contractColumns", "duplicateColumn", "high", f, col, 1))
            seen.add(col)
            if col not in allowed:
                out.append(Violation("contractColumns", "extraColumn", "high", f, col, 1))
        for col in sorted(set(required) - set(header)):
            out.append(Violation("contractColumns", "missingRequiredColumn", "high", f, col, 1))
    return Outcome(n=n, violations=tuple(out))


_VALIDATORS = {
    "hex64": re.compile(r"[0-9a-f]{64}").fullmatch,
    "integer": re.compile(r"-?\d+").fullmatch,
    "decimal": re.compile(r"-?\d+(?:\.\d+)?").fullmatch,
    "text": lambda s: True,
}


def _form_fn(form: str, params: dict):
    if form == "enum":
        values = params["values"]
        if not isinstance(values, list):
            raise TypeError("enum values must be a list")
        allowed = set(values)
        return allowed.__contains__
    if form in _VALIDATORS:
        return _VALIDATORS[form]
    if form.startswith("^") and form.endswith("$"):
        return re.compile(form).fullmatch
    raise ValueError("unknown form")  # neither a validator ID nor an anchored regex: contract invalid


@register(name="contractForms", version="1", scope="release", unit="cells")
def contract_forms_check(release, contract, context):
    files = contract_files(contract)
    out = []
    n = 0
    for f in release.csv_files:
        if f not in files:
            continue
        t = release.table(f)
        cols = files[f]["columns"]
        for idx, col in enumerate(t.header):
            if col not in cols:
                continue
            spec = cols[col]
            params = spec.get("params", {}) or {}
            ok = _form_fn(spec["form"], params)
            nullable = params.get("nullable", False) is True
            n += len(t.frame)
            if not len(t.frame):
                continue
            codes, uniques = release.factorized(f, idx)
            bad = np.array([not ((u == "" and nullable) or (u != "" and ok(u))) for u in uniques], dtype=bool)
            if bad.any():
                rows = np.nonzero(bad[codes])[0]
                out.append(Violation("contractForms", "formMismatch", "high", f, col, len(rows), locations(rows)))
    return Outcome(n=n, violations=tuple(out))


@register(name="fileDigests", version="1", scope="release", unit="files")
def file_digests_check(release, contract, context):
    """Gate phase: every release file must be readable and digestible (manifest not yet written).
    Verify phase (default): ``bindings.files`` must cover exactly the CSV files, each matching."""
    digests = {f: release.sha256(f) for f in release.csv_files}
    phase = context.get("phase", "verify")
    man = release.manifest()
    if phase == "gate" and man is None:
        return Outcome(n=len(digests), violations=())
    if man is None:
        return Outcome(n=max(len(digests), 1), violations=(
            Violation("fileDigests", "manifestMissing", "high", MANIFEST, None, 1),))
    bound = man["bindings"]["files"]
    if not isinstance(bound, dict):
        raise TypeError("bindings.files must be a mapping")
    out = []
    for f in sorted(set(digests) | set(bound)):
        if f not in bound:
            out.append(Violation("fileDigests", "digestMissing", "high", f, None, 1))
        elif f not in digests:
            out.append(Violation("fileDigests", "boundFileMissing", "high", f, None, 1))
        elif bound[f] != digests[f]:
            out.append(Violation("fileDigests", "digestMismatch", "high", f, None, 1))
    return Outcome(n=len(digests), violations=tuple(out))
