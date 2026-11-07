"""Pure column transforms, one per rung. Series in, Series out; no I/O, no globals.

Rules shared by all generalising rungs:
- null in -> null out (position preserved);
- a non-null value the rung cannot parse becomes ``""`` and is never passed through
  (a coarse rung must not leak the raw value);
- ``geo.full`` and ``keep`` are the only identity rungs; ``ts.exact``, ``num.exact`` and
  ``icd.full`` normalise to canonical text (offsets in ``ts.exact`` are dropped, not converted).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

import numpy as np
import pandas as pd

from .rungs import LadderError

_TS_RE = re.compile(
    r"^\s*(?:(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})|(?P<fd>\d{1,2})\.(?P<fm>\d{1,2})\.(?P<fy>\d{4}))"
    r"(?:(?:[ T]|\s+klo\s+)(?P<H>\d{1,2})[:.](?P<M>\d{2})(?:[:.](?P<S>\d{2}))?(?:\.\d+)?\s*(?:Z|[+-]\d{2}:?\d{2})?)?\s*$"
)


def _isnull(v: Any) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA


def _safe(fn: Callable[[str], str]) -> Callable[[str], str]:
    def run(v: str) -> str:
        try:
            return fn(v)
        except ArithmeticError:
            return ""  # beyond Decimal context: blank, never raise

    return run


def _mapped(s: pd.Series, fn: Callable[[str], str]) -> pd.Series:
    """Apply ``fn`` once per distinct non-null value; keep nulls and index."""
    fn = _safe(fn)
    uniq = {v: fn(v) for v in pd.unique(s.dropna())}
    return s.map(lambda v: v if _isnull(v) else uniq[v]).astype(object)


def _parse_ts(v: str) -> tuple[int, int, int, int, int, int] | None:
    """(year, month, day, hour, minute, second) of a fully valid timestamp/date string, or None."""
    m = _TS_RE.match(v)
    if not m:
        return None
    if m.group("y"):
        y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
    else:
        y, mo, d = int(m.group("fy")), int(m.group("fm")), int(m.group("fd"))
    h = int(m.group("H")) if m.group("H") else 0
    mi = int(m.group("M")) if m.group("M") else 0
    sec = int(m.group("S")) if m.group("S") else 0
    if not (1 <= mo <= 12 and 1 <= d <= 31 and 0 <= h <= 23 and 0 <= mi <= 59 and 0 <= sec <= 59):
        return None
    try:
        pd.Timestamp(year=y, month=mo, day=d)
    except (ValueError, OverflowError):
        return None
    return y, mo, d, h, mi, sec


def _ts_fmt(fn: Callable[..., str]) -> Callable[[pd.Series, dict], pd.Series]:
    def run(s: pd.Series, params: dict) -> pd.Series:
        def one(v: str) -> str:
            p = _parse_ts(v)
            return fn(*p) if p else ""

        return _mapped(s, one)

    return run


def _week(y: int, mo: int, d: int, *_: int) -> str:
    iso = pd.Timestamp(year=y, month=mo, day=d).isocalendar()
    return f"{int(iso.year):04d}-W{int(iso.week):02d}"


ts_exact = _ts_fmt(lambda y, mo, d, h, mi, sec: f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{sec:02d}")
ts_hour = _ts_fmt(lambda y, mo, d, h, *_: f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:00")
ts_month_hour = _ts_fmt(lambda y, mo, d, h, *_: f"{y:04d}-{mo:02d}-01T{h:02d}:00")
ts_hour_of_day = _ts_fmt(lambda y, mo, d, h, *_: f"{h:02d}:00")
ts_day = _ts_fmt(lambda y, mo, d, h, *_: f"{y:04d}-{mo:02d}-{d:02d}")
ts_week = _ts_fmt(_week)
ts_month = _ts_fmt(lambda y, mo, d, h, *_: f"{y:04d}-{mo:02d}")


def identity(s: pd.Series, params: dict) -> pd.Series:
    return s.copy()


# ------------------------------------------------------------------ lab test (D33, #106)
LAB_CRP_CODE = "P-CRP"  # the kit's CRP lab code; the toolkit's H-U7 selects CRP rows by test_code == this
LAB_REF_COLUMN = "test_code"


def lab_crp_other(s: pd.Series, params: dict, ref: pd.Series) -> pd.Series:
    """"CRP vs other": ``CRP`` where the same row's ``ref`` (the lab code, original values) equals
    ``params['code']`` (default ``P-CRP``), else ``other``. A null or empty source cell stays empty. The output
    holds only the two fixed labels, never a source value."""
    code = params.get("code", LAB_CRP_CODE)
    if not isinstance(code, str) or not code:
        raise LadderError("lab.crp_other code must be a non-empty string")
    out = []
    for v, r in zip(s.tolist(), ref.tolist()):
        if _isnull(v) or not str(v).strip():
            out.append("")
        else:
            out.append("CRP" if not _isnull(r) and str(r).strip() == code else "other")
    return pd.Series(out, index=s.index, dtype=object)


# ------------------------------------------------------------------ age
def _years_between(dob: tuple[int, int, int, int], ref: tuple[int, int, int, int]) -> int:
    return ref[0] - dob[0] - ((ref[1], ref[2]) < (dob[1], dob[2]))


def age_band(width: int) -> Callable[..., pd.Series]:
    """Band an age. ``source`` holds birth dates (or ages); ``ref`` is a same-index
    Series of reference timestamps, or None when ``params['ref_date']`` is used."""

    def run(s: pd.Series, params: dict, ref: pd.Series | None = None) -> pd.Series:
        fixed = None
        if ref is None:
            rd = params.get("ref_date")
            if not rd:
                raise LadderError("age rung needs params.ref_column or params.ref_date")
            fixed = _parse_ts(str(rd))
            if fixed is None:
                raise LadderError("params.ref_date is not a date")
        ref_parsed = None if ref is None else ref.map(lambda v: None if _isnull(v) else _parse_ts(str(v)))

        def band(age: int) -> str:
            if age < 0 or age > 130:
                return ""
            if age >= 90:
                return "90+"
            lo = age // width * width
            return f"{lo}-{lo + width - 1}"

        out = []
        for i, v in enumerate(s):
            if _isnull(v):
                out.append(v)
                continue
            t = str(v).strip()
            if re.fullmatch(r"\d{1,3}", t):
                out.append(band(int(t)))
                continue
            dob = _parse_ts(t)
            r = fixed if ref_parsed is None else ref_parsed.iloc[i]
            out.append(band(_years_between(dob, r)) if dob and r else "")
        return pd.Series(out, index=s.index, dtype=object)

    return run


age_band5 = age_band(5)
age_band10 = age_band(10)


# ------------------------------------------------------------------ geo
def geo_topn(s: pd.Series, params: dict) -> pd.Series:
    n = params.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise LadderError("geo.topn needs integer params.n >= 1")
    counts = s.dropna()[lambda x: x != ""].value_counts()
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    keep = {k for k, _ in ordered[:n]}
    return s.map(lambda v: v if _isnull(v) else (v if v == "" or v in keep else "other")).astype(object)


# ------------------------------------------------------------------ icd10
_ICD_RE = re.compile(r"^([A-Z])(\d{2})(?:\.?([A-Z0-9]{1,4}))?$")


def _icd(fn: Callable[[re.Match], str]) -> Callable[[pd.Series, dict], pd.Series]:
    def run(s: pd.Series, params: dict) -> pd.Series:
        def one(v: str) -> str:
            m = _ICD_RE.match(v.strip().upper())
            return fn(m) if m else ""

        return _mapped(s, one)

    return run


icd_full = _icd(lambda m: m.group(1) + m.group(2) + (f".{m.group(3)}" if m.group(3) else ""))
icd_3 = _icd(lambda m: m.group(1) + m.group(2))
icd_chapter = _icd(lambda m: m.group(1))


# ------------------------------------------------------------------ numeric
def _dec(v: str) -> Decimal | None:
    t = v.strip().replace(" ", "")
    if t.count(",") == 1 and "." not in t:
        t = t.replace(",", ".")
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _positive(params: dict, key: str) -> Decimal:
    raw = params.get(key)
    try:
        d = Decimal(str(raw))
    except InvalidOperation:
        raise LadderError(f"params.{key} must be a positive number") from None
    if raw is None or isinstance(raw, bool) or not d.is_finite() or d <= 0:
        raise LadderError(f"params.{key} must be a positive number")
    return d


def _decimals(*ds: Decimal) -> int:
    return max(0, *(-d.normalize().as_tuple().exponent for d in ds))


def _fmt(d: Decimal, places: int) -> str:
    q = Decimal(1).scaleb(-places)
    out = format(d.quantize(q), "f")
    return out[1:] if re.fullmatch(r"-0(\.0+)?", out) else out  # no negative zero


def num_exact(s: pd.Series, params: dict) -> pd.Series:
    """Canonical decimal text (dot separator, no exponent, optional < or > qualifier); unparseable -> empty."""

    def one(v: str) -> str:
        t = v.strip()
        q = t[0] if t[:1] in ("<", ">") else ""  # censored measurement ("<5") keeps its qualifier
        d = _dec(t[len(q):])
        if d is None:
            return ""
        out = q + format(d, "f")
        return re.sub(r"^([<>]?)-(0(?:\.0+)?)$", r"\1\2", out)

    return _mapped(s, one)


def num_round(s: pd.Series, params: dict) -> pd.Series:
    unit = _positive(params, "unit")
    places = _decimals(unit)

    def one(v: str) -> str:
        d = _dec(v)
        if d is None:
            return ""
        return _fmt((d / unit).to_integral_value(ROUND_HALF_UP) * unit, places)

    return _mapped(s, one)


def num_bin(s: pd.Series, params: dict) -> pd.Series:
    width = _positive(params, "width")
    raw_origin = params.get("origin", 0)
    try:
        origin = Decimal(str(raw_origin))
    except InvalidOperation:
        raise LadderError("params.origin must be a finite number") from None
    if raw_origin is None or isinstance(raw_origin, bool) or not origin.is_finite():
        raise LadderError("params.origin must be a finite number")
    places = _decimals(width, origin)

    def one(v: str) -> str:
        d = _dec(v)
        if d is None:
            return ""
        lo = ((d - origin) / width).to_integral_value(ROUND_FLOOR) * width + origin
        return f"[{_fmt(lo, places)},{_fmt(lo + width, places)})"

    return _mapped(s, one)
