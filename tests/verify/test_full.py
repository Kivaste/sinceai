"""Controller/auditor verify (``pets-release verify --full --kit <path> <release>``, key from PETS_HMAC_KEY).

Rule: exit 0 only if everything recipient mode checks holds AND every registered check (both scopes) and
every manifest-claimed check re-runs to pass AND the HMAC signature (06 manifest_signing_key) matches AND
every bound input digest matches the kit AND the bound tool revision is this checkout's.

Failure rows (trigger -> result):
  no --kit and no PETS_KIT                -> exit 2
  kit path missing                        -> exit 2
  PETS_HMAC_KEY unset / too short         -> exit 2
  signature value edited                  -> exit 1, signature
  signed with another key                 -> exit 1, signature
  valid-but-edited manifest (recipient passes) -> exit 1 under --full, signature
  kit table changed (input digest)        -> exit 1, inputs
  tool revision differs                   -> exit 1, toolRevision
  a check returns not_run                 -> exit 1, not_run
  claimed producer check unavailable / not runnable (real CLI) -> exit 1

In-process tests call the production ``verify_release`` with extra producer stubs (ticket 11's real checks
need run context that 21 supplies); the CLI tests use the registry as it is.
"""

from __future__ import annotations

import pytest

from pets_release.checks import Check, Outcome, all_checks
from pets_release.pseudonym import MasterKey


def _env(tb, kit=None, key=None):
    env = {}
    if key is not None:
        env["PETS_HMAC_KEY"] = key
    if kit is not None:
        env["PETS_KIT"] = str(kit)
    return env


def _stubs(tb, release, outcome=lambda: Outcome(n=1)):
    have = {c.name for c in all_checks()}
    out = []
    for rec in tb.load(release)["gate"]["checks"]:
        if rec["check"] not in have:
            out.append(Check(name=rec["check"], version=rec["version"], scope=rec["scope"],
                             unit=rec["denominator"]["unit"], run=lambda r, c, x, _o=outcome: _o()))
    return tuple(out)


def _full(tb, release, kit, checks=None, key=None):
    from pets_release.verify import verify_release

    return verify_release(release, full=True, kit=kit, master_key=MasterKey.from_text(key or tb.KEY),
                          checks=checks)


# --- CLI usage rows ---------------------------------------------------------------------------------------

def test_full_without_kit_exits_2(bed, verify_cli, tb):
    r = verify_cli("--full", bed, env=_env(tb, key=tb.KEY))
    assert r.returncode == 2
    assert "VERIFIED" not in r.stdout


def test_full_with_missing_kit_path_exits_2(bed, verify_cli, tb, tmp_path):
    r = verify_cli("--full", "--kit", tmp_path / "nokit", bed, env=_env(tb, key=tb.KEY))
    assert r.returncode == 2


@pytest.mark.parametrize("key", [None, "short"])
def test_full_without_key_exits_2(bed, kit, verify_cli, tb, key):
    r = verify_cli("--full", "--kit", kit, bed, env=_env(tb, key=key))
    assert r.returncode == 2
    assert "VERIFIED" not in r.stdout
    assert "short" not in r.stdout + r.stderr or key is None


def test_full_cli_fails_closed_on_unrunnable_producer_checks(bed, kit, verify_cli, tb):
    """Real CLI, real registry: producer checks are unregistered (before 11) or not_run (no producer context)."""
    r = verify_cli("--full", "--kit", kit, bed, env=_env(tb, key=tb.KEY))
    assert r.returncode == 1, r.stdout
    assert "producer." in r.stdout
    assert ("unavailable" in r.stdout) or ("not_run" in r.stdout)
    assert "VERIFIED (full)" not in r.stdout


def test_full_cli_bad_signature_fails(bed, kit, verify_cli, tb):
    m = tb.load(bed)
    m["signature"]["value"] = "f" * 64
    tb.save(bed, m)
    r = verify_cli("--full", "--kit", kit, bed, env=_env(tb, key=tb.KEY))
    assert r.returncode == 1
    assert "signature" in r.stdout


# --- in-process rows (production verify_release, stub producer checks) ------------------------------------

def test_full_pass_with_runnable_checks(bed, kit, tb):
    rep = _full(tb, bed, kit, checks=(*all_checks(), *_stubs(tb, bed)))
    assert rep.ok, rep.lines
    assert rep.lines[-1].startswith("VERIFIED (full):")


def test_full_bad_signature(bed, kit, tb):
    m = tb.load(bed)
    m["signature"]["value"] = "0" * 64
    tb.save(bed, m)
    rep = _full(tb, bed, kit, checks=(*all_checks(), *_stubs(tb, bed)))
    assert not rep.ok
    assert any("signature" in x for x in rep.lines)


def test_full_wrong_key(bed, kit, tb):
    rep = _full(tb, bed, kit, checks=(*all_checks(), *_stubs(tb, bed)), key="another-test-key-" + "1" * 32)
    assert not rep.ok
    assert any("signature" in x for x in rep.lines)


def test_valid_edit_passes_recipient_but_fails_full(bed, kit, tb, verify_cli):
    m = tb.load(bed)
    m["notFitFor"][0]["reason"] = "edited after signing"
    tb.save(bed, m)
    assert verify_cli(bed).returncode == 0  # the stated tamper limitation of recipient mode
    rep = _full(tb, bed, kit, checks=(*all_checks(), *_stubs(tb, bed)))
    assert not rep.ok
    assert any("signature" in x for x in rep.lines)


def test_full_input_digest_mismatch(bed, kit, tb):
    p = kit / "data" / "health" / "lab_results.csv"
    p.write_bytes(p.read_bytes() + b"L2\n")
    rep = _full(tb, bed, kit, checks=(*all_checks(), *_stubs(tb, bed)))
    assert not rep.ok
    assert any("inputs" in x for x in rep.lines)


def test_full_tool_revision_mismatch(bed, kit, tb):
    from pets_release.manifest import release_scope_id

    m = tb.load(bed)
    m["bindings"]["toolRevision"] = "1" * 40
    rel = m["release"]
    rel["releaseScopeId"] = release_scope_id(scenario=rel["scenario"], recipient=rel["recipient"],
                                             inputs=m["bindings"]["inputs"], tool_revision="1" * 40)
    tb.sign(m)
    tb.save(bed, m)
    rep = _full(tb, bed, kit, checks=(*all_checks(), *_stubs(tb, bed)))
    assert not rep.ok
    assert any("toolRevision" in x for x in rep.lines)


def test_full_not_run_check_fails(bed, kit, tb):
    rep = _full(tb, bed, kit, checks=(*all_checks(), *_stubs(tb, bed, outcome=Outcome.not_run)))
    assert not rep.ok
    assert any("not_run" in x for x in rep.lines)


def test_full_unavailable_claimed_check_fails(bed, kit, tb):
    stubs = _stubs(tb, bed)
    assert stubs, "fixture must claim producer checks"
    rep = _full(tb, bed, kit, checks=(*all_checks(), *stubs[1:]))
    assert not rep.ok
    assert any(stubs[0].name in x and "unavailable" in x for x in rep.lines)


def test_full_error_check_fails(bed, kit, tb):
    def boom():
        raise RuntimeError("x")

    rep = _full(tb, bed, kit, checks=(*all_checks(), *_stubs(tb, bed, outcome=boom)))
    assert not rep.ok
    assert any("error" in x for x in rep.lines)


# --- not_applicable (ticket 04 runner status) ----------------------------------------------------------------

def _na_check():
    return Check(name="text.verify-na-stub", version="1.0.0", scope="release", unit="turns",
                 run=lambda r, c, x: Outcome.not_applicable(), applies_to=("text",))


def test_not_applicable_is_accepted_and_counted(bed, tb):
    from pets_release.verify import verify_release

    rep = verify_release(bed, checks=(*all_checks(), _na_check()))
    assert rep.ok, rep.lines
    assert any(r.status == "not_applicable" for r in rep.records)


def test_only_not_applicable_fails(bed, tb):
    from pets_release.verify import verify_release

    rep = verify_release(bed, checks=(_na_check(),))
    assert not rep.ok
    assert any("nothing ran" in x for x in rep.lines)


def test_unlisted_planted_file_name_is_not_echoed(bed, verify_cli):
    (bed / "secret-name-4111111111111111.txt").write_bytes(b"x\n")
    r = verify_cli(bed)
    assert r.returncode == 1
    assert "4111111111111111" not in r.stdout + r.stderr
    assert "unlisted-file#" in r.stdout
