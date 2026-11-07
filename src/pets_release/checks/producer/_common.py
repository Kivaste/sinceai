"""Shared helpers for producer-scope checks (registered with ticket 04's registry).

Checks return 04's ``Outcome``; the runner builds the CheckRecord and decides the
status. A fail-closed condition raises ``CheckError``; the runner records any raise
as ``error`` with no message, so exception text (which could quote a value) never
leaves the check. Every CSV is read with ``dtype=str``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pets_release.checks.records import Violation, locations


class CheckError(Exception):
    """Fail-closed condition; the runner records it as status ``error``. Content-free text only."""


def viol(check: str, label: str, file: str, column: str, count: int, rows) -> Violation:
    return Violation(
        check=check, label=label, severity="high", file=file, column=column, count=int(count),
        locations=locations(rows),
    )


def release_dir(release) -> Path:
    p = Path(getattr(release, "path", release))  # 04's Release, or a folder path
    if not p.is_dir():
        raise CheckError("release folder missing")
    return p


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
