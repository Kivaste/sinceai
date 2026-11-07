"""Row-map validation. A row map is a scoring aid; the kit trusts it blindly, we do not."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

COLUMNS = ("protected_row", "original_record_id")


class RowMapRejected(ValueError):
    """The row map is not a faithful, complete map of the final protected rows."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_row_map(rowmap, *, protected_rows: int, source_keys: Iterable[str]) -> None:
    """Raise RowMapRejected unless the map covers exactly rows 0..protected_rows-1, once each,
    each pointing at a distinct existing source key."""
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
    if not keys.isin({str(k) for k in source_keys}).all():
        raise RowMapRejected("unknown_source_key")
