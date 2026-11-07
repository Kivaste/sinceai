"""#115 item 5: the minimiser reads the k target through the policy's ``k_target`` (seam: ``minimiser.search``).

Rule: the minimiser rejects exactly the k targets the pinned-policy function rejects (more than one
``k_anonymity`` target, a non-int / bool ``k``, or ``k < 2``), with the same content-free ValueError, before
any candidate is measured. It never searches against a malformed target. (A target with no ``k`` key is
refused earlier, by ``ScenarioPolicy`` itself.)

Failure rows (trigger -> wrong result before the fix):
  K1 k = 1, 0 or negative             -> CheckError from the downstream k checks, not the policy refusal
  K2 k a string / float / bool / None -> CheckError from the downstream k checks, not the policy refusal
  K3 two k_anonymity targets           -> a different message than the policy function's
"""
from __future__ import annotations

import pytest

from pets_release.minimiser import search
from pets_release.policy import k_target

MALFORMED = [1, 0, -3, "3", 3.0, True, None]


def _search(syn, pol):
    return search(pol, syn.tables, syn.keys, purpose=syn.purpose, params=syn.params, kspec=syn.kspec)


def _policy_error(pol) -> str:
    with pytest.raises(ValueError) as e:
        k_target(pol)
    return str(e.value)


def _assert_same_refusal(syn, pol):
    want = _policy_error(pol)
    with pytest.raises(ValueError) as e:
        _search(syn, pol)
    assert type(e.value) is ValueError and str(e.value) == want


@pytest.mark.parametrize("k", MALFORMED, ids=repr)
def test_malformed_or_below_two_k_rejected_like_policy(syn, k):
    _assert_same_refusal(syn, syn.policy(k=k))


def test_two_k_targets_rejected_like_policy(syn):
    pol = syn.policy()
    two = (*pol.privacy_targets, dict(pol.privacy_targets[0], id="qi-k2"))
    _assert_same_refusal(syn, type(pol)(**{**pol.__dict__, "privacy_targets": two}))


def test_valid_k_target_still_searches(syn):
    assert _search(syn, syn.policy(k=3)).plan  # the shared function accepts the int target >= 2
