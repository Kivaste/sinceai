"""Measure wiring with a search plan (ticket 25 x ticket 22's ``measure/wire.py``), production run on the minikit.

Rule: the measured release keeps the search's own ``measured.search`` (built from its log); the measurer fills
the other ``measured`` keys. Only the measurer's scoring is stubbed (it needs the kit). Rows:
  run_measured, plan_name None (search)  -> manifest measured.search measured, from the search log; utility from
                                            the measurer
  run_measured, plan_name "hand"          -> measured.search stays the measurer's (no search ran)
"""
from __future__ import annotations

import json

import pytest
from run_helpers import TEST_KEY, build_kit, grouped_qis, run_args

from pets_release.measure import wire
from pets_release.verify import current_tool_revision

BLOCK = {k: {"status": "not_measured", "reason": "stub"} for k in ("utility", "privacy", "baselines", "search", "redaction")}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=grouped_qis)
    monkeypatch.setattr(wire, "measure", lambda *a, **k: json.loads(json.dumps(BLOCK)))
    monkeypatch.setattr(wire, "person_k_components", lambda *a, **k: [])
    monkeypatch.setattr(wire, "_person_k_from_release", lambda **k: None)
    return kit, tmp_path / "rel"


def _run(kit, out, plan_name):
    from pets_release.cli import resolve_run_context

    ctx = resolve_run_context(run_args(kit, out)[1:])
    return wire.run_measured(kit=ctx.kit, scenario=ctx.scenario, created=ctx.created, key_text=ctx.key, out=out,
                             plan_name=plan_name, tool_revision=current_tool_revision())


def test_search_keeps_its_measured_search(setup):
    kit, out = setup
    res = _run(kit, out, None)
    assert res.status == "released"
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    s = m["measured"]["search"]
    log = [json.loads(x) for x in (out.parent / "rel.scoring" / "search_log.jsonl").read_text(
        encoding="utf-8").splitlines() if x]
    assert s["status"] == "measured" and s["candidates"] == len([e for e in log if e["step"] != "final"]) >= 1
    assert m["measured"]["utility"] == BLOCK["utility"]
    assert {f["source"] for f in m["fieldJustifications"]} == {"search"}


def test_hand_plan_keeps_the_measurer_search_block(setup):
    kit, out = setup
    res = _run(kit, out, "hand")
    assert res.status == "released"
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert m["measured"]["search"] == BLOCK["search"]
