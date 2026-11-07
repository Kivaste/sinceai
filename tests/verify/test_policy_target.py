"""#62 through the real CLI: a signed, internally consistent release that weakens the policy is refused.

Rows (trigger -> result), on a release built by the real ``pets-release run`` (synthetic minikit):
  unchanged                              -> verify --full exit 0, recipient verify exit 0
  contract k=2, re-bound and re-signed   -> verify --full exit 1, recipient verify exit 1 (manifest invalid)
  a released policy QI dropped from qi   -> verify --full exit 1, recipient verify exit 1
  extra column, derived_from malformed or naming a column outside the policy's source schema
                                         -> both tiers exit 1 (unknown-provenance)
"""
from __future__ import annotations

import pytest


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


def _add_column(real_bed, tb, params, name="at", src="arrival_ts"):
    """Copy a released QI column under a new name, declare it in the contract (not in qi, no justification)."""
    m = tb.load(real_bed.release)

    def edit(header, rows):
        i = header.index(src)
        return [*header, name], [[*r, r[i]] for r in rows]

    tb.edit_csv(real_bed.release, "ed_visits.csv", edit)
    cols = m["contract"]["files"]["ed_visits.csv"]["columns"]
    cols[name] = {"form": cols[src]["form"], "params": {**cols[src]["params"], **params}}
    real_bed.resign(m)


def test_unlisted_column_derived_from_policy_qi_fails_both_tiers(real_bed, verify_cli, tb):
    """Round-2 review (Sol): an extra arrival-derived column outside qi and the justifications."""
    _add_column(real_bed, tb, {"derived_from": "arrival_ts"})
    for full in (True, False):
        r = _verify(verify_cli, real_bed, full)
        assert r.returncode == 1, r.stdout
        assert "ed_visits.at: missing-policy-qi" in r.stdout


@pytest.mark.parametrize("ref", [".", "ed_visits.", "no_such_column", "lab_results.arrival_ts"])
def test_unresolvable_provenance_fails_both_tiers(real_bed, verify_cli, tb, ref):
    """Round-3 review (Sol): a malformed provenance reference, or one naming a source column absent from the
    pinned source schema (the policy's columns), is not provenance; it must not let a copied QI escape qi."""
    _add_column(real_bed, tb, {"derived_from": ref})
    for full in (True, False):
        r = _verify(verify_cli, real_bed, full)
        assert r.returncode == 1, r.stdout
        assert "ed_visits.at: unknown-provenance" in r.stdout, r.stdout


def test_column_without_provenance_fails_both_tiers(real_bed, verify_cli, tb):
    _add_column(real_bed, tb, {})
    for full in (True, False):
        r = _verify(verify_cli, real_bed, full)
        assert r.returncode == 1, r.stdout
        assert "ed_visits.at: no-provenance" in r.stdout
