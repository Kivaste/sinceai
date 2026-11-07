"""Closed, content-free operative numeric parameters for contracts and PET metadata."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pets_release.ladders import contract_entry


def numeric_params(rung, params):
    """Validate and copy the operative allowlist, never arbitrary plan metadata."""
    if rung == "geo.topn":
        if set(params) != {"n"} or type(params["n"]) is not int or params["n"] < 1:
            raise ValueError("numeric parameters: top-n invalid")
        return {"n": params["n"]}
    if rung not in ("num.exact", "num.round", "num.bin"):
        return {}
    required = {"unit"} if rung == "num.round" else ({"width"} if rung == "num.bin" else set())
    optional = {"origin"} if rung == "num.bin" else set()
    if not required <= set(params) or set(params) - required - optional:
        raise ValueError("numeric parameters: missing or unknown key")
    result = dict(params)
    if rung == "num.bin":
        result.setdefault("origin", 0)
    for key, raw in result.items():
        _number(raw, positive=key != "origin")
    return result


def validate_numeric_spec(form, params):
    """Contracts require all effective parameters, even defaults optional in a plan."""
    rung = params.get("rung")
    numeric = rung == "geo.topn" or (isinstance(rung, str) and rung.startswith("num."))
    if not numeric:
        if set(params) & {"unit", "width", "origin", "n"}:
            raise ValueError("numeric parameters: rung missing or mismatched")
        return
    operative = numeric_params(rung, {k: v for k, v in params.items() if k not in ("rung", "nullable")})
    if (set(params) != {"rung", "nullable"} | set(operative)
            or params.get("nullable") is not True or form != contract_entry(rung)["form"]):
        raise ValueError("numeric parameters: incomplete or mismatched contract")


def _number(raw, *, positive):
    if type(raw) not in (int, float, str):
        raise ValueError("numeric parameters: number invalid")
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise ValueError("numeric parameters: number invalid") from None
    if not value.is_finite() or (positive and value <= 0):
        raise ValueError("numeric parameters: number invalid")
