"""Row-map validation. A row map is a scoring aid; the kit trusts it blindly, we do not.

Two strengths of check:
- Structural (no lineage given): the map covers exactly rows 0..n-1 once each, with distinct,
  existing source keys. This CANNOT detect swapped keys or a retained row mapped to the wrong
  (e.g. suppressed) record: only the writer knows which source record each final row came from.
- Lineage (the writer's `Lineage` given): the map must equal the writer's final-row -> source-key
  table exactly, and the writer's suppressed set must account for every unmapped source key.
  Release and measurement paths must supply it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

COLUMNS = ("protected_row", "original_record_id")


class RowMapRejected(ValueError):
    """The row map is not a faithful, complete map of the final protected rows."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Lineage:
    """Writer-supplied truth: `final[i]` is the source key of final protected row i;
    `suppressed` is the set of source keys the writer dropped."""

    final: tuple[str, ...]
    suppressed: frozenset[str]


def validate_row_map(rowmap, *, protected_rows: int, source_keys: Iterable[str],
                     expected_lineage: Lineage | None = None) -> None:
    """Raise RowMapRejected unless the map is valid (see module docstring)."""
    if isinstance(rowmap, (str, Path)):
        rowmap = pd.read_csv(rowmap, dtype=str, keep_default_na=False)
    if not isinstance(rowmap, pd.DataFrame) or any(c not in rowmap.columns for c in COLUMNS):
        raise RowMapRejected("structure")
    rows = rowmap["protected_row"].astype(str).str.strip()
    keys = rowmap["original_record_id"].astype(str)
    if not rows.str.fullmatch(r"\d+").all():
        raise RowMapRejected("bad_row_index")
    idx = rows.astype(int)
    if idx.duplicated().any():
        raise RowMapRejected("duplicate_row")
    if (idx >= protected_rows).any():
        raise RowMapRejected("unknown_protected_row")
    if len(idx) < protected_rows:
        raise RowMapRejected("missing_row")
    if keys.duplicated().any():
        raise RowMapRejected("duplicate_source_key")
    source = {str(k) for k in source_keys}
    if not keys.isin(source).all():
        raise RowMapRejected("unknown_source_key")
    if expected_lineage is not None:
        _check_lineage(dict(zip(idx, keys, strict=True)), protected_rows, source, expected_lineage)


def _check_lineage(mapping: dict[int, str], protected_rows: int, source: set[str], lin: Lineage) -> None:
    if len(lin.final) != protected_rows or len(set(lin.final)) != len(lin.final):
        raise RowMapRejected("lineage_mismatch")
    if set(mapping.values()) & set(lin.suppressed):
        raise RowMapRejected("suppressed_row_mapped")
    if set(lin.final) | set(lin.suppressed) != source or set(lin.final) & set(lin.suppressed):
        raise RowMapRejected("suppression_mismatch")
    if any(mapping[i] != lin.final[i] for i in range(protected_rows)):
        raise RowMapRejected("lineage_mismatch")
