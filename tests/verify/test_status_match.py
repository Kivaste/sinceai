"""Verify fails when a re-run check's status differs from the status the manifest's gate record attests.

Failure rows (trigger -> result), in recipient mode and under --full:
  manifest pass, re-run not_applicable   -> exit 1, status mismatch
  manifest not_applicable, re-run pass   -> exit 1, status mismatch
  statuses equal (pass/pass, na/na)      -> unaffected
Synthetic fixture rows only; the in-process tests call the production ``verify_release``.
"""

from __future__ import annotations

from pets_release.checks import Check, Outcome, all_checks
from pets_release.pseudonym import MasterKey

RELEASE_CHECK = "contract.columns"  # not assertion-backing, so its record may be edited
PRODUCER_CHECK = "producer.original-values"


def _na(rec_or_chk, name=None):
    """Same name/version/scope/unit, but re-runs to not_applicable (declared form absent from the contract)."""
    c = rec_or_chk
    return Check(name=c.name, version=c.version, scope=c.scope, unit=c.unit,
                 run=lambda r, k, x: Outcome.not_applicable(), applies_to=("no-such-form",))


def _set_status(tb, bed, check, status):
    m = tb.load(bed)
    for rec in m["gate"]["checks"]:
        if rec["check"] == check:
            rec["status"] = status
            rec["denominator"]["n"] = 0 if status == "not_applicable" else 1
    tb.sign(m)
    tb.save(bed, m)


def _recipient_checks(swap=None):
    return tuple(swap if swap is not None and c.name == swap.name else c for c in all_checks())


def _producer_stubs(tb, bed, na_name=None):
    out = []
    for rec in tb.load(bed)["gate"]["checks"]:
        if rec["scope"] == "producer":
            kw = {"name": rec["check"], "version": rec["version"], "scope": "producer", "unit": rec["denominator"]["unit"]}
            if rec["check"] == na_name:
                out.append(Check(**kw, run=lambda r, k, x: Outcome.not_applicable(), applies_to=("no-such-form",)))
            else:
                out.append(Check(**kw, run=lambda r, k, x: Outcome(n=1)))
    return tuple(out)


def _full_checks(tb, bed, na_name=None):
    stubs = _producer_stubs(tb, bed, na_name)
    names = {s.name for s in stubs}
    return tuple(c for c in all_checks() if c.scope != "producer" and c.name not in names) + stubs


def _full(tb, bed, kit, checks):
    from pets_release.verify import verify_release

    # fixture rows are not a run of the kit: purpose re-run stubbed (real CLI coverage: tests/run/test_purpose_gate.py)
    return verify_release(bed, full=True, kit=kit, master_key=MasterKey.from_text(tb.KEY), checks=checks,
                          purpose=lambda *a: [])


def _mismatch(rep):
    return any("status mismatch" in x for x in rep.lines)


# --- recipient mode ---------------------------------------------------------------------------------------

def test_recipient_manifest_pass_rerun_not_applicable_fails(bed):
    from pets_release.verify import verify_release

    chk = next(c for c in all_checks() if c.name == RELEASE_CHECK)
    rep = verify_release(bed, checks=_recipient_checks(_na(chk)))
    assert not rep.ok
    assert _mismatch(rep), rep.lines


def test_recipient_manifest_not_applicable_rerun_pass_fails(bed, tb):
    from pets_release.verify import verify_release

    _set_status(tb, bed, RELEASE_CHECK, "not_applicable")
    rep = verify_release(bed)
    assert not rep.ok
    assert _mismatch(rep), rep.lines


def test_recipient_matching_not_applicable_still_passes(bed, tb):
    from pets_release.verify import verify_release

    _set_status(tb, bed, RELEASE_CHECK, "not_applicable")
    chk = next(c for c in all_checks() if c.name == RELEASE_CHECK)
    rep = verify_release(bed, checks=_recipient_checks(_na(chk)))
    assert rep.ok, rep.lines


def test_recipient_cli_manifest_not_applicable_rerun_pass_fails(bed, verify_cli, tb):
    _set_status(tb, bed, RELEASE_CHECK, "not_applicable")
    r = verify_cli(bed)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "status mismatch" in r.stdout
    assert "VERIFIED" not in r.stdout.replace("VERIFY FAILED", "")


# --- --full -------------------------------------------------------------------------------------------------

def test_full_manifest_pass_rerun_not_applicable_fails(bed, kit, tb):
    rep = _full(tb, bed, kit, _full_checks(tb, bed, na_name=PRODUCER_CHECK))
    assert not rep.ok
    assert _mismatch(rep), rep.lines


def test_full_manifest_not_applicable_rerun_pass_fails(bed, kit, tb):
    _set_status(tb, bed, PRODUCER_CHECK, "not_applicable")
    rep = _full(tb, bed, kit, _full_checks(tb, bed))
    assert not rep.ok
    assert _mismatch(rep), rep.lines


def test_full_release_check_not_applicable_rerun_pass_fails(bed, kit, tb):
    _set_status(tb, bed, RELEASE_CHECK, "not_applicable")
    rep = _full(tb, bed, kit, _full_checks(tb, bed))
    assert not rep.ok
    assert _mismatch(rep), rep.lines


def test_full_matching_statuses_still_pass(real_bed):
    """#71: real registry and producer context (no stubs) on a real run release: attested == re-run."""
    from pets_release.kit import Kit
    from pets_release.run.context import verify_context
    from pets_release.verify import verify_release

    master = MasterKey.from_text(real_bed.KEY)
    rep = verify_release(real_bed.release, full=True, kit=real_bed.kit, master_key=master,
                         context=verify_context(Kit(real_bed.kit), master, real_bed.release))
    assert rep.ok, rep.lines
    assert not _mismatch(rep)
    assert {r.check for r in rep.records if r.scope == "producer"} >= {
        "producer.key-material", "producer.original-values", "producer.person-k", "producer.unkeyed-hashes"}


def test_full_attested_status_mismatch_on_real_bed_fails(real_bed, tb):
    """#71: on the real bed, a producer record attested not_applicable while the real check passes -> mismatch."""
    from pets_release.kit import Kit
    from pets_release.run.context import verify_context
    from pets_release.verify import verify_release

    m = tb.load(real_bed.release)
    for rec in m["gate"]["checks"]:
        if rec["check"] == "producer.original-values":
            rec.update(status="not_applicable", hits=0)
            rec["denominator"]["n"] = 0
    real_bed.resign(m)
    master = MasterKey.from_text(real_bed.KEY)
    rep = verify_release(real_bed.release, full=True, kit=real_bed.kit, master_key=master,
                         context=verify_context(Kit(real_bed.kit), master, real_bed.release))
    assert not rep.ok
    assert any("producer.original-values" in x and "status mismatch" in x for x in rep.lines), rep.lines
