"""Row-map-lineage adapter (D21 fallback): restore source turn_ids on a protected turns table so the
kit's CS-U5 (which matches by turn_id) can score it. Used only for the labelled "adapted" score."""
from __future__ import annotations

import pandas as pd


class LineageError(ValueError):
    """Row map does not cover the protected rows exactly. Content-free."""


def restore_turn_ids(protected_turns: pd.DataFrame, rowmap: pd.DataFrame) -> pd.DataFrame:
    """Copy of ``protected_turns`` (positional rows 0..n-1) with ``turn_id`` set from the row map
    (``protected_row`` -> ``original_record_id``). The map must cover every row exactly once and
    name each original at most once."""
    if set(rowmap.columns) != {"protected_row", "original_record_id"}:
        raise LineageError("row map columns")
    n = len(protected_turns)
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
    out = protected_turns.reset_index(drop=True).copy()
    out["turn_id"] = [by_row[i] for i in range(n)]
    return out
