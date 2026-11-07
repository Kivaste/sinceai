"""Recipient-mode verify (``pets-release verify <release>``), through the real CLI.

Rule: exit 0 and print exactly ``VERIFIED (limited): N release-checked, M producer-attested`` only if the
manifest validates (02), every bound file digest matches, every manifest-claimed release-scope check is
registered at the claimed version, and every registered release-scope check re-runs to pass. Anything
else exits 1 (2 for a missing path). Never prints unqualified success.

Failure rows (trigger -> result):
  changed release file (digest mismatch)          -> exit 1, file-digest failure
  planted card, digests re-bound                  -> exit 1, rescan.payment-cards fails (gate pass not reused)
  extra column, digests re-bound                  -> exit 1, contract.columns fails
  edited manifest: assertion true / unknown key / non-canonical bytes / digest edit -> exit 1, manifest invalid
  missing manifest                                -> exit 1
  claimed release check not registered            -> exit 1, unavailable
  claimed check version differs from registry     -> exit 1
  missing release path                            -> exit 2
"""

from __future__ import annotations

import json
import re

LIMITED = re.compile(r"^VERIFIED \(limited\): (\d+) release-checked, (\d+) producer-attested$", re.MULTILINE)


def _release_checks():
    from pets_release.checks import all_checks

    return all_checks("release")


def _assert_never_unqualified(out: str):
    for line in out.splitlines():
        if "VERIFIED" in line.upper() and "FAILED" not in line.upper():
            assert line.startswith("VERIFIED (limited):"), line


def test_pass_prints_limited_with_counts(bed, verify_cli, tb):
    r = verify_cli(bed)
    assert r.returncode == 0, r.stdout + r.stderr
    m = LIMITED.search(r.stdout)
    assert m, r.stdout
    n_release = len(_release_checks())
    n_producer = sum(1 for c in tb.load(bed)["gate"]["checks"] if c["scope"] == "producer")
    assert (int(m.group(1)), int(m.group(2))) == (n_release, n_producer)
    assert n_release >= 1 and n_producer >= 1
    _assert_never_unqualified(r.stdout + r.stderr)


def test_failure_never_prints_success(bed, verify_cli):
    (bed / "ed_visits.csv").write_bytes((bed / "ed_visits.csv").read_bytes() + b"\n")
    r = verify_cli(bed)
    assert r.returncode == 1
    assert not LIMITED.search(r.stdout)
    assert "VERIFY FAILED" in r.stdout
    _assert_never_unqualified(r.stdout + r.stderr)


def test_changed_file_fails(bed, verify_cli, tb):
    tb.edit_csv(bed, "lab_results.csv", lambda h, rows: (h, [rows[0][:3] + ["6"] + rows[0][4:]] + rows[1:]))
    r = verify_cli(bed)
    assert r.returncode == 1
    assert "digest" in r.stdout


def test_planted_card_fails_even_with_rebound_digests(bed, verify_cli, tb):
    i = None

    def plant(h, rows):
        nonlocal i
        i = h.index("value")
        rows[0][i] = "4111111111111111"  # Luhn-valid test card; fits the column's digit form
        return h, rows

    tb.edit_csv(bed, "lab_results.csv", plant)
    m = tb.rebind_files(bed, tb.load(bed))
    tb.save(bed, m)  # manifest still says gate pass for rescan.payment-cards: must not be reused
    r = verify_cli(bed)
    assert r.returncode == 1, r.stdout
    assert "rescan.payment-cards" in r.stdout
    assert "4111111111111111" not in r.stdout + r.stderr  # content-free output


def test_extra_column_fails(bed, verify_cli, tb):
    tb.edit_csv(bed, "ed_visits.csv", lambda h, rows: (h + ["extra_col"], [r + ["1"] for r in rows]))
    tb.save(bed, tb.rebind_files(bed, tb.load(bed)))
    r = verify_cli(bed)
    assert r.returncode == 1
    assert "contract.columns" in r.stdout


def test_planted_file_in_release_fails(bed, verify_cli):
    (bed / "notes.txt").write_bytes(b"x\n")
    r = verify_cli(bed)
    assert r.returncode == 1
    assert "contract.files" in r.stdout


def _edit_manifest(bed, tb, fn):
    m = tb.load(bed)
    fn(m)
    tb.save(bed, m)


def test_manifest_assertion_true_fails(bed, verify_cli, tb):
    _edit_manifest(bed, tb, lambda m: m["exportAssertions"].__setitem__("paymentCards", True))
    r = verify_cli(bed)
    assert r.returncode == 1
    assert "manifest" in r.stdout


def test_manifest_unknown_key_fails(bed, verify_cli, tb):
    _edit_manifest(bed, tb, lambda m: m.__setitem__("verified", True))
    assert verify_cli(bed).returncode == 1


def test_manifest_noncanonical_bytes_fail(bed, verify_cli, tb):
    m = tb.load(bed)
    (bed / tb.MANIFEST).write_text(json.dumps(m, indent=1), encoding="utf-8")
    assert verify_cli(bed).returncode == 1


def test_manifest_digest_edit_fails(bed, verify_cli, tb):
    _edit_manifest(bed, tb, lambda m: m["bindings"]["files"].__setitem__("ed_visits.csv", "a" * 64))
    r = verify_cli(bed)
    assert r.returncode == 1
    assert "digest" in r.stdout


def test_missing_manifest_fails(bed, verify_cli, tb):
    (bed / tb.MANIFEST).unlink()
    assert verify_cli(bed).returncode == 1


def test_claimed_release_check_not_registered_fails(bed, verify_cli, tb):
    def add(m):
        rec = {"check": "release.not-registered", "version": "1.0.0", "scope": "release", "status": "pass",
               "denominator": {"unit": "files", "n": 1}, "hits": 0}
        m["gate"]["checks"] = sorted(m["gate"]["checks"] + [rec], key=lambda r: r["check"])
        m["bindings"]["checkVersions"]["release.not-registered"] = "1.0.0"

    _edit_manifest(bed, tb, add)
    r = verify_cli(bed)
    assert r.returncode == 1
    assert "release.not-registered" in r.stdout and "unavailable" in r.stdout


def test_claimed_version_mismatch_fails(bed, verify_cli, tb):
    def bump(m):
        for rec in m["gate"]["checks"]:
            if rec["check"] == "contract.files":
                rec["version"] = "9.9.9"
        m["bindings"]["checkVersions"]["contract.files"] = "9.9.9"

    _edit_manifest(bed, tb, bump)
    r = verify_cli(bed)
    assert r.returncode == 1
    assert "contract.files" in r.stdout and "version" in r.stdout


def test_missing_release_path_is_usage_error(tmp_path, verify_cli):
    r = verify_cli(tmp_path / "nope")
    assert r.returncode == 2
    assert "VERIFIED" not in r.stdout


def test_kit_without_full_is_usage_error(bed, kit, verify_cli):
    assert verify_cli("--kit", kit, bed).returncode == 2


def test_unmodified_02_fixture_is_not_silently_trusted(verify_cli, tb):
    """The committed 02 fixture claims release-scope checks this registry does not have (yet): fail closed."""
    from pets_release.checks import all_checks

    claimed = {c["check"] for c in tb.load(tb.FIXTURE)["gate"]["checks"] if c["scope"] == "release"}
    missing = claimed - {c.name for c in all_checks()}
    r = verify_cli(tb.FIXTURE)
    if missing:
        assert r.returncode == 1
        assert "unavailable" in r.stdout
    else:
        assert r.returncode in (0, 1)
