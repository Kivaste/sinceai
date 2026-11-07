"""Detector-derived QI set of a release (#106, decision D33). Schema names only; values stay in memory.

A released column is a detector QI when the detector classifies it as ``quasi_identifier`` either

* on its released values (every released table, detected together so foreign-key links count), which never
  reads declared provenance, so a column whose declared source is wrong is still classified by what it holds; or
* through its declared source column in the source tables (``params.derived_from`` of its contract column,
  ``col`` or ``table.col``, else the column itself), so a coarsened QI still counts.

Producer person-k refuses when one of these is missing from ``contract.qi`` (the producer context carries the set).
"""
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from .inventory import detect_dataset

QI_ROLE = "quasi_identifier"


def _source_of(table: str, column: str, spec) -> tuple[str, str]:
    params = spec.get("params") if isinstance(spec, Mapping) else None
    declared = params.get("derived_from") if isinstance(params, Mapping) else None
    if isinstance(declared, str) and declared:
        t, _, c = declared.rpartition(".")
        return (t or table, c)
    return (table, column)


def released_qis(source: Mapping[str, pd.DataFrame], released: Mapping[str, pd.DataFrame],
                 contract: Mapping, unverified=()) -> list[dict]:
    """``[{table, column}]`` of every released column that is a detector QI (sorted). Raises on detector failure.
    ``unverified``: (table, column) pairs whose declared source did not reproduce them (``run.provenance``); with no
    trusted source they count as QIs (fail closed)."""
    files = (contract or {}).get("files") or {}
    src_qi = {(r["table"], r["column"]) for r in detect_dataset("source", dict(source)) if r["role"] == QI_ROLE}
    out = {(r["table"], r["column"]) for r in detect_dataset("release", dict(released)) if r["role"] == QI_ROLE}
    out |= {(t, str(c)) for t, c in unverified}
    for t, df in released.items():
        cols = (files.get(f"{t}.csv") or {}).get("columns") or {}
        for c in df.columns:
            if _source_of(t, str(c), cols.get(c)) in src_qi:
                out.add((t, str(c)))
    return [{"table": t, "column": c} for t, c in sorted(out)]
