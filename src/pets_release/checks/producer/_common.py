"""Shared helpers for producer-scope checks: CheckRecord building and release reading.

Seam (until ticket 04's registry lands): each check is a ``Check`` with
``name, version, scope, run(release, contract, context) -> CheckRecord``.
``release`` is a release folder path; every CSV is read with ``dtype=str``.
Records follow the spec's pinned CheckRecord shape exactly and never carry values.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

LOCATION_CAP = 100  # same cap as ticket 04's records.MAX_LOCATIONS


@dataclass(frozen=True)
class Check:
    name: str
    version: str
    scope: str  # "release" | "producer"
    run: Callable[[Any, dict, dict], dict]


class CheckError(Exception):
    """Fail-closed condition found while running a check; recorded as status ``error``.

    Messages must be content-free (schema names and counts only).
    """


def violation(check, label, file, column, locations, severity="high"):
    locs = sorted(set(locations), key=lambda x: (str(type(x)), x))
    return {
        "check": check,
        "label": label,
        "severity": severity,
        "file": file,
        "column": column,
        "count": len(locs) if locs else 0,
        "locations": locs[:LOCATION_CAP],
    }


def record(check: Check, status, unit, n, hits=0, violations=()):
    vs = sorted(violations, key=lambda v: (v["file"], v["column"], v["label"]))
    return {
        "check": check.name,
        "version": check.version,
        "scope": check.scope,
        "status": status,
        "denominator": {"unit": unit, "n": int(n)},
        "hits": int(hits),
        "violations": vs,
    }


def guarded(check_ref: Callable[[], Check], unit: str):
    """Wrap a run function so any exception becomes an ``error`` record (fail closed).

    Like ticket 04's runner, the record carries the status only: exception text
    (which may quote a value, e.g. a parse error) is never copied anywhere.
    """

    def deco(fn):
        def run(release, contract, context):
            try:
                return fn(release, contract, context or {})
            except Exception:  # noqa: BLE001  (message may carry values; record the status only)
                return record(check_ref(), "error", unit, 0)

        return run

    return deco


def not_run(check: Check, unit: str):
    return record(check, "not_run", unit, 0)


def release_dir(release) -> Path:
    p = Path(getattr(release, "path", release))  # a folder path or ticket 04's Release
    if not p.is_dir():
        raise CheckError("release folder missing")
    return p


def release_csvs(release) -> list[Path]:
    return sorted(release_dir(release).glob("*.csv"), key=lambda p: p.name)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)


def read_table(release, table: str) -> pd.DataFrame:
    path = release_dir(release) / f"{table}.csv"
    if not path.is_file():
        raise CheckError("released table file missing")
    return read_csv(path)


def qi_by_table(contract: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for q in (contract or {}).get("qi", []) or []:
        out.setdefault(q["table"], [])
        if q["column"] not in out[q["table"]]:
            out[q["table"]].append(q["column"])
    return {t: sorted(cols) for t, cols in sorted(out.items())}
