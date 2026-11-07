"""CS-S1 purpose checks under ``run.purpose.evaluate`` (#60), real kit-eval adapter on the synthetic minikit.

Rule: a record key the scenario lists for purpose lineage (CS-S1: turns.turn_id) and that is released as a
release-scope pseudonym is restored through the producer row map (token inversion, ``run.context``) before the
purpose checks score the release; the score without it is disclosed as an ungated ``<task>.unmodified`` entry.
The CS-U5 sacrifice floor is the policy's.

Rows (trigger -> result):
  pseudonymised turn_id + producer row maps      -> accepted; CS-U5 after >= floor; CS-U5.unmodified after 0.0
  pseudonymised turn_id, no row maps              -> refused purpose:CS-U5:below-sacrifice-floor (fail closed)
  row map not covering the released turns         -> refused purpose:lineage:error
  turn_id kept as-is (contract does not tokenise) -> no row map for turns, no .unmodified entries; accepted
  policy                                          -> CS-U1, CS-U3, CS-U4, CS-U5; sacrifice CS-U5 floor 0.8
"""
from __future__ import annotations

import pytest
from cs_kit import build_cs_kit

from pets_release.contract import generate
from pets_release.policy import get_policy
from pets_release.pseudonym import MasterKey
from pets_release.run.context import DEFAULT_RECIPIENT, producer_context
from pets_release.run.purpose import evaluate

POLICY = get_policy("CS-S1")
RSID = "0123456789abcdef"  # conftest's release scope
TEST_KEY = "test-only-master-key-0123456789abcdef"  # conftest's synthetic test key, not a secret


@pytest.fixture(scope="module")
def kit(tmp_path_factory):
    return build_cs_kit(tmp_path_factory.mktemp("cskit") / "kit")


def _released(p):
    return {k: v.reset_index(drop=True).astype(str) for k, v in p.tables.items()}


def _rowmaps(p, source):
    ctx = producer_context(scenario_id="CS-S1", policy=POLICY, source=source, master=MasterKey.from_text(TEST_KEY),
                           scope_id=RSID, recipient=DEFAULT_RECIPIENT, contract=generate(POLICY, p.plan),
                           released=_released(p))
    return ctx["rowmaps"]


def test_policy_lists_cs_purpose_checks_and_u5_floor():
    assert POLICY.purpose_checks == ("CS-U1", "CS-U3", "CS-U4", "CS-U5")
    assert [(s["check"], s["floor_score"]) for s in POLICY.sacrifices] == [("CS-U5", 0.8)]


def test_pseudonymised_turn_id_scored_through_row_map(prepared, minikit, kit):
    rm = _rowmaps(prepared, minikit)
    assert "turns" in rm
    res = evaluate(POLICY, minikit, _released(prepared), root=kit, rowmaps=rm)
    assert res.ok, res.reasons
    t = {x["task"]: x for x in res.tasks}
    assert {"CS-U1", "CS-U3", "CS-U4", "CS-U5"} <= set(t)
    assert t["CS-U5"]["after"] >= 0.8
    assert t["CS-U5.unmodified"]["after"] == 0.0 and t["CS-U5.unmodified"]["before"] == t["CS-U5"]["before"]


def test_pseudonymised_turn_id_without_row_map_refuses(prepared, minikit, kit):
    res = evaluate(POLICY, minikit, _released(prepared), root=kit)
    assert "purpose:CS-U5:below-sacrifice-floor" in res.reasons


def test_row_map_not_covering_turns_refuses(prepared, minikit, kit):
    rm = dict(_rowmaps(prepared, minikit))
    rm["turns"] = rm["turns"].iloc[1:]
    res = evaluate(POLICY, minikit, _released(prepared), root=kit, rowmaps=rm)
    assert res.reasons == ("purpose:lineage:error",)


def test_run_refuses_and_publishes_nothing_when_purpose_fails(tmp_path, monkeypatch, kit):
    """Production ``run_release`` for CS-S1; only the evaluation's verdict is replaced by a failing one."""
    from cs_kit import cs_run_args

    from pets_release.cli import resolve_run_context
    from pets_release.run import pipeline, purpose
    from pets_release.verify import current_tool_revision

    real = purpose.evaluate
    seen = {}

    def failing(policy, source, released, *, root, rowmaps=None):
        res = real(policy, source, released, root=root, rowmaps=rowmaps)
        seen["rowmaps"] = sorted(rowmaps or {})
        return purpose.PurposeResult(res.tasks, ("purpose:CS-U5:below-sacrifice-floor",), res.lineage)

    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    monkeypatch.setattr(purpose, "evaluate", failing)
    out = tmp_path / "rel"
    ctx = resolve_run_context(cs_run_args(kit, out)[1:])
    with pytest.raises(pipeline.RunRefused):
        pipeline.run_release(kit=ctx.kit, scenario=ctx.scenario, created=ctx.created, key_text=ctx.key, out=out,
                             plan_name="hand", tool_revision=current_tool_revision())
    assert "turns" in seen["rowmaps"]  # the run passes the producer row maps
    assert not out.exists()
    assert (tmp_path / "rel.scoring" / "refusal_report.json").is_file()


def test_kept_turn_id_needs_no_lineage(kept, kit):
    src = kept.gate_context["source"]
    rm = _rowmaps(kept, src)
    assert "turns" not in rm
    res = evaluate(POLICY, src, _released(kept), root=kit, rowmaps=rm)
    assert res.ok, res.reasons
    assert not [x for x in res.tasks if x["task"].endswith(".unmodified")]
