"""D33 (#106): the lab-test ladder, full name -> "CRP vs other" -> withheld. Synthetic values only.

Rows (trigger -> result):
  lab.crp_other on a table with the lab code   -> CRP exactly where the same row's code is P-CRP, else other; a null
                                                  or empty name stays empty; only the two fixed labels appear
  params.code given                            -> that code is the CRP code
  ref_column absent from the table / bad code  -> LadderError (fail closed), never a guess
  ladder order                                 -> lab.full finer than lab.crp_other finer than withheld
"""
from __future__ import annotations

import re

import pandas as pd
import pytest

from pets_release.ladders import LADDERS, LadderError, apply, at_least_as_coarse, contract_form


class _NoKeys:
    def token(self, value, label="RECORD_KEY"):
        raise AssertionError("no pseudonyms here")


def _run(rung, names, codes, params=None, with_code=True):
    cols = {"name": names, **({"code": codes} if with_code else {})}
    df = pd.DataFrame(cols, dtype=object)
    plan = [{"table": "t", "column": "name", "rung": rung, "params": params if params is not None else
             {"ref_column": "code"}, "floor": "lab.full"}]
    if with_code:
        plan.append({"table": "t", "column": "code", "rung": "withheld", "params": {}, "floor": "keep"})
    return apply(plan, {"t": df}, _NoKeys())


def test_crp_exactly_where_the_code_is_crp():
    out = _run("lab.crp_other", ["alpha", "beta", "gamma", "", None], ["P-CRP", "X-1", "P-CRP", "P-CRP", "X-1"])
    assert list(out["t"].columns) == ["name"]
    assert out["t"]["name"].tolist() == ["CRP", "other", "CRP", "", ""]


def test_code_param_and_fixed_labels_only():
    out = _run("lab.crp_other", ["a", "b"], ["Z-9", "P-CRP"], {"ref_column": "code", "code": "Z-9"})["t"]["name"]
    assert out.tolist() == ["CRP", "other"]
    assert set(out) <= {"CRP", "other", ""}
    assert all(re.fullmatch(contract_form("lab.crp_other"), v) for v in out if v)


@pytest.mark.parametrize("params", [{"ref_column": "missing"}, {"ref_column": "code", "code": ""},
                                    {"ref_column": "code", "code": 5}, {"ref_column": 3}])
def test_bad_params_fail_closed(params):
    with pytest.raises(LadderError):
        _run("lab.crp_other", ["a"], ["P-CRP"], params)


def test_default_ref_column_absent_fails_closed():
    with pytest.raises(LadderError):
        _run("lab.crp_other", ["a"], None, {}, with_code=False)


def test_ladder_order():
    assert LADDERS["lab_test"] == ("lab.full", "lab.crp_other", "withheld")
    assert at_least_as_coarse("lab.crp_other", "lab.full") and not at_least_as_coarse("lab.full", "lab.crp_other")
    assert not at_least_as_coarse("keep", "lab.full")  # another ladder never satisfies the floor
