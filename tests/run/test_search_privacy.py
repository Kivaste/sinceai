"""Run-side guard on the search's final privacy re-check (ticket 25 after ticket 24's f2cef36).

Rule: `run` releases a search plan only if the search's final re-check says privacy ``pass`` for exactly the
policy's declared targets, each ``pass``; ``not_applicable`` only when the policy declares no target. Rows:
  status pass, targets == policy targets, all pass   -> accepted
  status fail / error / unsupported target            -> RunRefused
  status not_applicable but the policy declares one   -> RunRefused
  status not_applicable, policy declares none, []     -> accepted
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
