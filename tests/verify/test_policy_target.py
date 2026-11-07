"""#62 through the real CLI: a signed, internally consistent release that weakens the policy is refused.

Rows (trigger -> result), on a release built by the real ``pets-release run`` (synthetic minikit):
  unchanged                              -> verify --full exit 0, recipient verify exit 0
  contract k=2, re-bound and re-signed   -> verify --full exit 1, recipient verify exit 1 (manifest invalid)
  a released policy QI dropped from qi   -> verify --full exit 1, recipient verify exit 1
"""
from __future__ import annotations


def _verify(verify_cli, real_bed, full):
    args = ["--full", "--kit", real_bed.kit, real_bed.release] if full else [real_bed.release]
    return verify_cli(*args, env=real_bed.env())


def test_unchanged_real_release_verifies(real_bed, verify_cli):
    for full in (True, False):
        r = _verify(verify_cli, real_bed, full)
        assert r.returncode == 0, r.stdout + r.stderr


def test_weakened_k_fails_both_tiers(real_bed, verify_cli, tb):
    m = tb.load(real_bed.release)
    assert m["contract"]["k"] == 5
    m["contract"]["k"] = 2
    real_bed.resign(m)
    for full in (True, False):
        r = _verify(verify_cli, real_bed, full)
        assert r.returncode == 1, r.stdout
        assert "contract.k" in r.stdout


def test_omitted_policy_qi_fails_both_tiers(real_bed, verify_cli, tb):
    m = tb.load(real_bed.release)
    qi = m["contract"]["qi"]
    drop = sorted(q["column"] for q in qi)[0]
    m["contract"]["qi"] = [q for q in qi if q["column"] != drop]
    real_bed.resign(m)
    for full in (True, False):
        r = _verify(verify_cli, real_bed, full)
        assert r.returncode == 1, r.stdout
        assert "missing-policy-qi" in r.stdout
