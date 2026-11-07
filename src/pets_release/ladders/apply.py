"""``apply(plan, tables, keys)``: pure, plan-driven application of the rungs."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import pandas as pd

from . import transforms as T
from .rungs import CONTRACT_FORMS, KNOWN_RUNGS, WITHHELD, LadderError, coarseness


class KeyMaterial(Protocol):
    """Pseudonymiser seam (ticket 06 sits behind it). Release scope is bound inside."""

    def token(self, value: str, label: str = "RECORD_KEY") -> str: ...


Redactor = Callable[[str, str, pd.DataFrame, Mapping[str, Any]], pd.Series]

DEFAULT_AGE_COLUMN = "age_band"

_SIMPLE: dict[str, Callable[[pd.Series, dict], pd.Series]] = {
    "ts.exact": T.ts_exact,
    "ts.hour": T.ts_hour,
    "ts.month_hour": T.ts_month_hour,
    "ts.hour_of_day": T.ts_hour_of_day,
    "ts.day": T.ts_day,
    "ts.week": T.ts_week,
    "ts.month": T.ts_month,
    "geo.full": T.identity,
    "geo.topn": T.geo_topn,
    "icd.full": T.icd_full,
    "icd.3": T.icd_3,
    "icd.chapter": T.icd_chapter,
    "num.exact": T.num_exact,
    "num.round": T.num_round,
    "num.bin": T.num_bin,
    "keep": T.identity,
}
_AGE = {"age.band5": T.age_band5, "age.band10": T.age_band10}


def _null(v: Any) -> bool:
    return v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v))


def _token(keys: KeyMaterial, value: str, label: str) -> str:
    t = keys.token(value, label)
    if not isinstance(t, str) or not re.fullmatch(r"[0-9a-f]{64}", t):
        raise LadderError("pseudonymiser returned a token that is not hex64")
    return t


def output_column(entry: Mapping[str, Any]) -> str:
    """Name of the column a plan entry produces (differs from the source for age bands)."""
    if entry["rung"] in _AGE:
        return (entry.get("params") or {}).get("output") or DEFAULT_AGE_COLUMN
    return entry["column"]


def _validate(plan: list[Mapping[str, Any]], tables: Mapping[str, pd.DataFrame]) -> dict[tuple[str, str], Mapping[str, Any]]:
    by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for e in plan:
        key = (e["table"], e["column"])
        if key in by_key:
            raise LadderError(f"duplicate plan entry for {key[0]}.{key[1]}")
        if e["table"] not in tables or e["column"] not in tables[e["table"]].columns:
            raise LadderError(f"plan entry for unknown column {key[0]}.{key[1]}")
        rung = e["rung"]
        if rung not in KNOWN_RUNGS:
            raise LadderError(f"unknown rung {rung!r} for {key[0]}.{key[1]}")
        floor = e.get("floor")
        if not isinstance(floor, str) or floor not in KNOWN_RUNGS:
            raise LadderError(f"missing or unknown floor for {key[0]}.{key[1]}")
        if floor == WITHHELD:
            ok = rung == WITHHELD
        elif rung == WITHHELD:
            ok = True
        else:
            (rk, rp), (fk, fp) = coarseness(rung), coarseness(floor)
            ok = rk == fk and rp >= fp
        if not ok:
            raise LadderError(f"rung {rung!r} is finer than its floor {floor!r} for {key[0]}.{key[1]}")
        by_key[key] = e
    for t, df in tables.items():
        for c in df.columns:
            if (t, c) not in by_key:
                raise LadderError(f"no plan entry for {t}.{c}")
    return by_key


def apply(
    plan: list[Mapping[str, Any]],
    tables: Mapping[str, pd.DataFrame],
    keys: KeyMaterial,
    *,
    redactor: Redactor | None = None,
) -> dict[str, pd.DataFrame]:
    """Apply a plan to string tables and return the generalised tables.

    Pure: inputs are not mutated, there is no I/O, plan order does not matter, and rows keep
    their order and index. Columns keep source order; an age rung replaces its source column
    with a derived column. Tables whose columns are all withheld are omitted; a table with no columns is refused. A redactor result is realigned by index (same labels, any order) or refused. An age rung's output name may not equal any source column of its table. Fail closed:
    every source column needs exactly one plan entry, every rung must be known and not finer
    than its floor, and ``text.redacted`` needs an injected ``redactor(table, column, frame,
    params) -> Series`` (ticket 12).
    """
    for tname, df in tables.items():
        if len(df.columns) == 0:
            raise LadderError(f"table {tname} has no columns")
    by_key = _validate(list(plan), tables)
    out: dict[str, pd.DataFrame] = {}
    for tname in sorted(tables):
        src = tables[tname]
        cols: dict[str, pd.Series] = {}
        for col in src.columns:
            e = by_key[(tname, col)]
            rung, params = e["rung"], dict(e.get("params") or {})
            if rung == WITHHELD:
                continue
            name = output_column(e)
            if name in cols or (name != col and name in src.columns) or (rung in _AGE and name in src.columns):
                raise LadderError(f"output column collision on {tname}.{name}")
            s = src[col]
            if not all(isinstance(v, str) or _null(v) for v in pd.unique(s)):
                raise LadderError(f"non-string cells in {tname}.{col}; tables must be read with dtype=str")
            if rung in _AGE:
                ref = None
                if params.get("ref_column"):
                    rc = params["ref_column"]
                    if rc not in src.columns:
                        raise LadderError(f"age ref_column unknown in table {tname}")
                    ref = src[rc]  # original values, not the generalised column
                res = _AGE[rung](s, params, ref)
            elif rung == "id.pseudonym":
                label = params.get("label", "RECORD_KEY")
                res = s.map(lambda v, label=label: v if _null(v) or v == "" else _token(keys, str(v), label))
            elif rung == "text.redacted":
                if redactor is None:
                    raise LadderError("text.redacted needs a redactor")
                res = redactor(tname, col, src, params)
                if not isinstance(res, pd.Series) or len(res) != len(src):
                    raise LadderError("redactor must return a Series aligned to the table")
                if not res.index.equals(src.index):
                    if res.index.is_unique and src.index.is_unique and res.index.isin(src.index).all():
                        res = res.reindex(src.index)
                    else:
                        raise LadderError("redactor result index does not match the table index")
            else:
                res = _SIMPLE[rung](s, params)
            cols[name] = res.astype(object)
        if cols:
            out[tname] = pd.DataFrame(cols, index=src.index)
    return out


assert set(_SIMPLE) | set(_AGE) | {"id.pseudonym", "text.redacted"} == set(CONTRACT_FORMS)
