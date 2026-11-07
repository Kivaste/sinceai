"""Run-side guard on the search's final privacy re-check (ticket 25 after ticket 24's f2cef36).

Rule: `run` releases a search plan only if the search's final re-check says privacy ``pass`` for exactly the
policy's declared targets, each ``pass``; ``not_applicable`` only when the policy declares no target. Rows:
  status pass, targets == policy targets, all pass   -> accepted
  status fail / error / unsupported target            -> RunRefused
  status not_applicable but the policy declares one   -> RunRefused
  status not_applicable, policy declares none, []     -> accepted
  status not_applicable with a non-empty target list  -> RunError (self-contradiction)
  status pass but a policy target missing / extra     -> RunError (contradiction: unknown state)
  status pass but a target not pass                    -> RunError
  privacy_status or privacy_targets key missing        -> RunError
"""
from __future__ import annotations

import types

import pytest

from pets_release.run.pipeline import RunError, RunRefused, check_search_privacy

K = {"id": "qi-k", "kind": "k_anonymity", "k": 5, "unit": "persons"}
POL = types.SimpleNamespace(privacy_targets=(K,))
NONE = types.SimpleNamespace(privacy_targets=())


def _final(status, targets):
    return {"privacy_status": status, "privacy_targets": targets}


def test_pass_accepted():
    check_search_privacy(_final("pass", [{"id": "qi-k", "kind": "k_anonymity", "status": "pass"}]), POL)


@pytest.mark.parametrize("status,tstatus", [("fail", "fail"), ("fail", "error"), ("fail", "unsupported")])
def test_not_pass_refuses(status, tstatus):
    with pytest.raises(RunRefused):
        check_search_privacy(_final(status, [{"id": "qi-k", "kind": "k_anonymity", "status": tstatus}]), POL)


def test_not_applicable_with_declared_target_refuses():
    with pytest.raises(RunRefused):
        check_search_privacy(_final("not_applicable", []), POL)


def test_not_applicable_without_targets_accepted():
    check_search_privacy(_final("not_applicable", []), NONE)


@pytest.mark.parametrize("policy", [NONE, POL], ids=["no-declared", "declared"])
def test_not_applicable_with_a_target_list_is_unknown_state(policy):
    """A re-check that says not_applicable yet lists targets contradicts itself: RunError, not a refusal."""
    with pytest.raises(RunError):
        check_search_privacy(_final("not_applicable", [{"id": "qi-k", "kind": "k_anonymity", "status": "pass"}]),
                             policy)


@pytest.mark.parametrize("targets", [
    [],
    [{"id": "qi-k", "kind": "k_anonymity", "status": "pass"}, {"id": "x", "kind": "k_anonymity", "status": "pass"}],
    [{"id": "qi-k", "kind": "k_anonymity", "status": "fail"}],
    [{"id": "qi-k", "kind": "other", "status": "pass"}],
])
def test_pass_contradicting_targets_is_unknown_state(targets):
    with pytest.raises(RunError):
        check_search_privacy(_final("pass", targets), POL)


@pytest.mark.parametrize("final", [{}, {"privacy_status": "pass"}, {"privacy_targets": []}, None])
def test_missing_keys_is_unknown_state(final):
    with pytest.raises(RunError):
        check_search_privacy(final, POL)


# --- the production CLI (`pets-release run`, no --plan) with the search's result altered at its return ---------
# Rows (trigger -> result): the real search runs on the synthetic minikit once; its SearchResult.final is then
# replaced at the boundary where `run` receives it.
#   final privacy fail / error / unsupported target    -> exit 1, no release folder
#   not_applicable although the policy declares a target -> exit 1, no release folder
#   pass but a target missing / extra / not pass        -> exit 2, no release folder
#   keys missing / targets not a list / final not a dict -> exit 2, no release folder
#   the unaltered result                                -> exit 0 (control: the boundary hook itself is neutral)

_CACHE: dict = {}


def _targets(status, *, kind=None):
    from pets_release.policy import get_policy

    return [{"id": t["id"], "kind": kind or t["kind"], "status": status} for t in get_policy("HEALTH-S1").privacy_targets]


CASES = {
    "fail": (1, lambda f: dict(f, privacy_status="fail", privacy_targets=_targets("fail"))),
    "error": (1, lambda f: dict(f, privacy_status="error", privacy_targets=_targets("error"))),
    "unsupported": (1, lambda f: dict(f, privacy_status="unsupported", privacy_targets=_targets("unsupported"))),
    "not-applicable": (1, lambda f: dict(f, privacy_status="not_applicable", privacy_targets=[])),
    "pass-missing-target": (2, lambda f: dict(f, privacy_status="pass", privacy_targets=[])),
    "pass-extra-target": (2, lambda f: dict(f, privacy_status="pass", privacy_targets=_targets("pass") + [
        {"id": "extra", "kind": "k_anonymity", "status": "pass"}])),
    "pass-target-fails": (2, lambda f: dict(f, privacy_status="pass", privacy_targets=_targets("fail"))),
    "pass-wrong-kind": (2, lambda f: dict(f, privacy_status="pass", privacy_targets=_targets("pass", kind="x"))),
    "no-status": (2, lambda f: {k: v for k, v in f.items() if k != "privacy_status"}),
    "no-targets": (2, lambda f: {k: v for k, v in f.items() if k != "privacy_targets"}),
    "targets-not-list": (2, lambda f: dict(f, privacy_targets="pass")),
    "final-not-dict": (2, lambda f: None),
}


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    """Run `pets-release run` in-process with `pipeline.search` returning the real search's result, altered."""
    import copy
    import dataclasses

    from run_helpers import TEST_KEY, build_kit, grouped_qis

    from pets_release.run import pipeline

    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", grouped_qis)
    real = pipeline.search

    def run(alter):
        def altered(*a, **k):
            if "res" not in _CACHE:
                _CACHE["res"] = real(*a, **k)
            res = copy.deepcopy(_CACHE["res"])
            return dataclasses.replace(res, final=alter(res.final))

        monkeypatch.setattr(pipeline, "search", altered)
        from pets_release.cli import main

        out = tmp_path / "out" / "rel"
        code = main(["run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out),
                     "--created", "2026-11-07T00:00:00Z"])
        return code, out

    return run


@pytest.mark.parametrize("case", sorted(CASES))
def test_cli_refuses_an_altered_search_privacy_record(boundary, case):
    want, alter = CASES[case]
    code, out = boundary(alter)
    assert code == want
    assert not out.exists()
    assert not out.parent.exists() or not list(out.parent.rglob("privacy_manifest.json"))


def test_cli_releases_the_unaltered_search_result(boundary):
    code, out = boundary(lambda f: f)
    assert code == 0
    assert (out / "privacy_manifest.json").is_file()
