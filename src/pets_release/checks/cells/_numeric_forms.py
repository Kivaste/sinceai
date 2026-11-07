"""Independent numeric grid checks; never call the release transformer."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction

_DECIMAL = re.compile(r"-?\d+(?:\.\d+)?")
_INTERVAL = re.compile(r"\[(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)\)")


def numeric_form(form, params):
    rung = params.get("rung")
    if rung == "geo.topn":
        if (form != "text" or set(params) != {"nullable", "rung", "n"}
                or params.get("nullable") is not True or type(params["n"]) is not int or params["n"] < 1):
            raise ValueError("top-n contract parameters invalid")
        return None  # the cross-cell cardinality bound is checked by contract.forms
    if rung not in ("num.exact", "num.round", "num.bin"):
        if set(params) & {"unit", "width", "origin", "n"} or (isinstance(rung, str) and rung.startswith("num.")):
            raise ValueError("numeric contract rung missing or invalid")
        return None
    keys = {"unit"} if rung == "num.round" else ({"width", "origin"} if rung == "num.bin" else set())
    if set(params) != {"nullable", "rung"} | keys or params.get("nullable") is not True:
        raise ValueError("numeric contract parameters invalid")
    if rung == "num.exact":
        if form != r"^[<>]?-?\d+(?:\.\d+)?$":
            raise ValueError("exact numeric contract form invalid")
        return None
    if rung == "num.round":
        if form != "decimal":
            raise ValueError("rounding contract form invalid")
        unit = _number(params["unit"], positive=True)

        def matches(value):
            return bool(_DECIMAL.fullmatch(value)) and Fraction(value) % unit == 0

        return matches
    if form != r"^\[-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?\)$":
        raise ValueError("binning contract form invalid")
    width = _number(params["width"], positive=True)
    origin = _number(params["origin"], positive=False)

    def matches(value):
        interval = _INTERVAL.fullmatch(value)
        if interval is None:
            return False
        lo, hi = map(Fraction, interval.groups())
        return hi - lo == width and (lo - origin) % width == 0

    return matches


def _number(raw, *, positive):
    if type(raw) not in (int, float, str):
        raise ValueError("numeric contract number invalid")
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise ValueError("numeric contract number invalid") from None
    if not value.is_finite() or (positive and value <= 0):
        raise ValueError("numeric contract number invalid")
    return Fraction(value)
