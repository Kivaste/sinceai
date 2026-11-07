"""#115 item 5 at the run seam: ``pets-release run`` (in-process ``run.cli.main``) on the synthetic minikit
with the pinned HEALTH-S1 policy's k target made malformed. Synthetic rows only.

Rule: a malformed or < 2 policy k target is never released against: the run refuses with the contract
generator's content-free ``policy: k target invalid`` before any release folder is written. The pinned policy is
swapped in-process (a subprocess cannot be handed a non-pinned policy); everything else is the production run
path.

Failure rows (trigger -> wrong result):
  R1 policy k target 1 / 0 / "5" / True / two targets -> a release folder written, or a run that returns
"""
from __future__ import annotations

import dataclasses

import pytest
from run_helpers import TEST_KEY, build_kit, coarse_qis, run_args

from pets_release.contract.generate import ContractError
from pets_release.policy import get_policy

BAD = {"k1": [1], "k0": [0], "kstr": ["5"], "kbool": [True], "two": [5, 5]}


def _bad_policy(ks):
    pol = get_policy("HEALTH-S1")
    k = next(t for t in pol.privacy_targets if t["kind"] == "k_anonymity")
    rest = [t for t in pol.privacy_targets if t["kind"] != "k_anonymity"]
    targets = [dict(k, k=v, id=f"{k['id']}-{i}" if i else k["id"]) for i, v in enumerate(ks)]
    sup = dict(pol.suppression, k=ks[0]) if pol.suppression else pol.suppression
    return dataclasses.replace(pol, privacy_targets=tuple(rest + targets), suppression=sup)


@pytest.mark.parametrize("case", sorted(BAD))
def test_run_refuses_malformed_policy_k_target(case, tmp_path, monkeypatch):
    from pets_release.run import cli, pipeline

    bad = _bad_policy(BAD[case])
    monkeypatch.setattr(pipeline, "get_policy", lambda sid: bad)
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", coarse_qis)
    out = tmp_path / "out" / "rel"
    with pytest.raises(ContractError, match=r"^policy: k target invalid$"):
        cli.main(run_args(kit, out)[1:])
    assert not out.exists()
