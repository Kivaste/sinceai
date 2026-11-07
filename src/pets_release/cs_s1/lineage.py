"""Row-map lineage (D21 fallback): restore source record keys on a protected table so a kit purpose check that
matches by that key (CS-U5 matches by turn_id) can score it. ``run.purpose`` uses it with the producer row maps."""
from __future__ import annotations

import pandas as pd


class LineageError(ValueError):
    """Row map does not cover the protected rows exactly. Content-free."""


def restore_record_keys(protected: pd.DataFrame, rowmap: pd.DataFrame, column: str) -> pd.DataFrame:
    """Copy of ``protected`` (positional rows 0..n-1) with ``column`` set from the row map
    (``protected_row`` -> ``original_record_id``). The map must cover every row exactly once and
    name each original at most once."""
    if set(rowmap.columns) != {"protected_row", "original_record_id"}:
        raise LineageError("row map columns")
    if column not in protected.columns:
        raise LineageError("record key column missing from the protected table")
    n = len(protected)
    try:
        rows = rowmap["protected_row"].astype(str).map(int)
    except ValueError:
        raise LineageError("row map protected_row not integer") from None
    if len(rowmap) != n or sorted(rows) != list(range(n)):
        raise LineageError("row map does not cover the protected rows exactly")
    orig = rowmap["original_record_id"].astype(str)
    if orig.duplicated().any() or (orig.str.strip() == "").any():
        raise LineageError("row map original ids duplicated or empty")
    by_row = dict(zip(rows, orig))
    out = protected.reset_index(drop=True).copy()
    out[column] = [by_row[i] for i in range(n)]
    return out


def restore_turn_ids(protected_turns: pd.DataFrame, rowmap: pd.DataFrame) -> pd.DataFrame:
    return restore_record_keys(protected_turns, rowmap, "turn_id")
