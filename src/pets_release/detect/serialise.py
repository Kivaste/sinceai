"""Two serialisers over one inventory. Headers are copied from the kit:
`dataset,table,column,privacy_role,subtype` (pets-eval detect) and `column,privacy_role,subtype` (unseen)."""

from __future__ import annotations

import csv
import io

KIT_HEADER = ["dataset", "table", "column", "privacy_role", "subtype"]
UNSEEN_HEADER = ["column", "privacy_role", "subtype"]
KIT_HEADER_LINE = ",".join(KIT_HEADER)
UNSEEN_HEADER_LINE = ",".join(UNSEEN_HEADER)


def _write(header: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def to_kit_csv(inventory: list[dict]) -> str:
    rows = sorted(inventory, key=lambda r: (r["dataset"], r["table"], r["column"]))
    return _write(KIT_HEADER, [[r["dataset"], r["table"], r["column"], r["role"], r["subtype"]] for r in rows])


def to_unseen_csv(inventory: list[dict]) -> str:
    """Column order of the source table is kept (one table only)."""
    tables = {r["table"] for r in inventory}
    if len(tables) > 1:
        raise ValueError("unseen format carries no table name, so it needs exactly one table")
    return _write(UNSEEN_HEADER, [[r["column"], r["role"], r["subtype"]] for r in inventory])
