"""k comes from the release contract's top-level ``k``; context k must agree; no contract k -> not_applicable (CS-S1 has no k target; ticket 23)."""

from __future__ import annotations

import pytest

from pets_release.checks import all_checks, run_checks
from pets_release.run.context import person_normaliser

VISITS = [f"V{i}" for i in range(6)]
SEX = ["F"] * 3 + ["M"] * 3  # two classes of 3


def _run(name, rel, contract, ctx):
    (chk,) = [c for c in all_checks() if c.name == name]
    return run_checks(rel, contract, ctx, checks=[chk]).to_dict()["records"][0]


@pytest.fixture
def setup(h):
    rel = h.release({"ed_visits": {"sex": SEX}})
    ctx = {
        "source": {"ed_visits": h.frame({"visit_id": VISITS, "patient_hetu": [f"P{i}" for i in range(6)]})},
        "rowmaps": {"ed_visits": h.rowmap(VISITS)},
        "record_keys": {"ed_visits": "visit_id"},
        "person": {"table": "ed_visits", "column": "patient_hetu", "normalise": person_normaliser()},
        "joins": [],
    }
    return rel, ctx


NAMES = ["producer.person-k", "producer.row-k"]


@pytest.mark.parametrize("name", NAMES)
def test_k_is_read_from_the_contract(h, setup, name):
    rel, ctx = setup
    assert _run(name, rel, h.contract([("ed_visits", "sex")], k=3), ctx)["status"] == "pass"
    assert _run(name, rel, h.contract([("ed_visits", "sex")], k=4), ctx)["status"] == "fail"


@pytest.mark.parametrize("name", NAMES)
def test_context_k_must_equal_contract_k(h, setup, name):
    rel, ctx = setup
    c = h.contract([("ed_visits", "sex")], k=3)
    assert _run(name, rel, c, dict(ctx, k=3))["status"] == "pass"
    assert _run(name, rel, c, dict(ctx, k=2))["status"] == "error"


@pytest.mark.parametrize("name", NAMES)
def test_no_contract_k_is_not_applicable_even_with_context_k(h, setup, name):
    rel, ctx = setup
    assert _run(name, rel, h.contract([("ed_visits", "sex")], k=None), dict(ctx, k=2))["status"] == "not_applicable"


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("bad", [1, 0, "5", 2.0, True, None])
def test_invalid_contract_k_is_an_error(h, setup, name, bad):
    rel, ctx = setup
    c = h.contract([("ed_visits", "sex")]) | {"k": bad}
    assert _run(name, rel, c, ctx)["status"] == "error"
