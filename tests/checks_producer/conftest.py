"""Shared synthetic fixtures for producer-check tests.

All rows are hand-made synthetic values; nothing is copied from the kit.
"""

from __future__ import annotations

import types

import pandas as pd
import pytest


def _write_release(root, tables):
    root.mkdir(parents=True, exist_ok=True)
    for name, cols in tables.items():
        pd.DataFrame(cols, dtype=str).to_csv(root / f"{name}.csv", index=False)
    return root


def _rowmap(ids):
    return pd.DataFrame(
        {"protected_row": [str(i) for i in range(len(ids))], "original_record_id": list(ids)},
        dtype=str,
    )


def _contract(qi, tokens=(), k=5):
    c = {} if k is None else {"k": k}
    return c | {
        "files": {},
        "qi": [{"table": t, "column": c, "derived_from": f"{t}.{c}"} for t, c in qi],
        "tokens": [{"table": t, "column": c, "scope": "release"} for t, c in tokens],
    }


def _frame(cols):
    return pd.DataFrame(cols, dtype=str)


@pytest.fixture
def h(tmp_path):
    """Helpers: h.release(tables, name), h.rowmap(ids), h.contract(qi, tokens), h.frame(cols)."""
    counter = {"n": 0}

    def release(tables, name=None):
        counter["n"] += 1
        return _write_release(tmp_path / (name or f"release{counter['n']}"), tables)

    return types.SimpleNamespace(release=release, rowmap=_rowmap, contract=_contract, frame=_frame)
